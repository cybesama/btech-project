"""
WebSocket endpoint — one connection per browser session.

Message protocol
----------------
Browser → Server (JSON string):
  {"type": "frame",   "data": "<base64-JPEG>"}
  {"type": "command", "cmd":  "<command-string>"}

Server → Browser (JSON string):
  {"action": "speak",    "text": "...", "state": "...", "objects": [...]}
  {"action": "describe", "objects": [...]}   ← triggers SSE call from frontend
  {"action": "idle",     "objects": [...]}
"""

import base64
import json
from dataclasses import dataclass, field
from time import time
from typing import List, Literal, Optional

import cv2
import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.services.food_api import format_product_speech, lookup_barcode
from backend.services.ocr_service import read_text, scan_barcode
from backend.services.yolo_service import yolo_service

router = APIRouter()

# ── Timing constants ──────────────────────────────────────────────────────────
_ALERT_COOLDOWN = 3.0       # seconds between collision alerts
_DESCRIBE_INTERVAL = 30.0   # seconds between auto AI-descriptions
_GUIDANCE_COOLDOWN = 5.0    # seconds between shopping guidance utterances
_SCAN_COOLDOWN = 5.0        # seconds between "what do I see?" announcements


# ── Session state ─────────────────────────────────────────────────────────────

@dataclass
class ShoppingSession:
    state: str = "scanning"          # "scanning" | "guiding" | "explaining"
    target_item: Optional[str] = None
    target_bbox: Optional[List[int]] = None
    last_spoken_at: float = 0.0
    last_explained_barcode: Optional[str] = None   # avoid re-reading same barcode
    shopping_list: List[str] = field(default_factory=list)


@dataclass
class ClientSession:
    mode: str = "navigation"         # "navigation" | "shopping" | "describe"
    last_alert_time: float = 0.0
    last_describe_time: float = 0.0
    shopping: ShoppingSession = field(default_factory=ShoppingSession)


# ── Shopping helpers ──────────────────────────────────────────────────────────

def _announce_items(objects: List[dict]) -> str:
    if not objects:
        return "I don't see any items clearly right now. Move the camera slowly across the shelf."

    by_zone: dict = {"left": [], "center": [], "right": []}
    for o in objects:
        by_zone.setdefault(o.get("zone", "center"), []).append(o["name"])

    parts = []
    if by_zone["left"]:
        parts.append(", ".join(by_zone["left"]) + " on your left")
    if by_zone["center"]:
        parts.append(", ".join(by_zone["center"]) + " directly ahead")
    if by_zone["right"]:
        parts.append(", ".join(by_zone["right"]) + " on your right")

    count = len(objects)
    prefix = f"I can see {count} item{'s' if count > 1 else ''} — "
    return prefix + "; ".join(parts) + "."


def _match_item(target: str, objects: List[dict]) -> Optional[dict]:
    t = target.lower()
    for o in objects:
        if t in o["name"].lower() or o["name"].lower() in t:
            return o
    return None


def _guidance(target_bbox: List[int], frame_shape: tuple, distance: Optional[float]) -> str:
    h, w = frame_shape[:2]
    x1, y1, x2, y2 = target_bbox
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    fill = ((x2 - x1) * (y2 - y1)) / (w * h)

    if fill > 0.35 or (distance and distance < 0.5):
        return "Item is right in front of you. Grab it now."

    parts = []
    horiz = cx - w // 2
    vert = cy - h // 2

    if abs(horiz) > w * 0.15:
        parts.append("move your hand left" if horiz < 0 else "move your hand right")
    if abs(vert) > h * 0.15:
        parts.append("tilt slightly up" if vert < 0 else "tilt slightly down")

    if distance and distance > 1.5:
        parts.append("step a bit closer")
    elif not parts:
        parts.append("reach forward")

    return "Getting closer — " + ", ".join(parts) + "."


# ── Per-frame shopping logic ──────────────────────────────────────────────────

async def _process_shopping(frame: np.ndarray, shop: ShoppingSession) -> dict:
    now = time()

    if shop.state == "scanning":
        objects = yolo_service.detect_center_region(frame)
        if now - shop.last_spoken_at >= _SCAN_COOLDOWN:
            shop.last_spoken_at = now
            return {"action": "speak", "text": _announce_items(objects),
                    "state": "scanning", "objects": objects}
        return {"action": "idle", "objects": objects}

    elif shop.state == "guiding":
        objects = yolo_service.detect_center_region(frame)
        matched = _match_item(shop.target_item, objects) if shop.target_item else None

        if not matched:
            if now - shop.last_spoken_at >= 3.0:
                shop.last_spoken_at = now
                return {"action": "speak",
                        "text": f"I lost sight of the {shop.target_item}. "
                                "Sweep the camera slowly left and right.",
                        "state": "guiding"}
            return {"action": "idle"}

        shop.target_bbox = matched["bbox"]
        dist = matched.get("distance")

        # Try barcode first every frame (fast check)
        barcode = scan_barcode(frame)
        box = matched["bbox"]
        fill = ((box[2] - box[0]) * (box[3] - box[1])) / (frame.shape[1] * frame.shape[0])

        if barcode or fill > 0.35:
            shop.state = "explaining"
            if barcode and barcode != shop.last_explained_barcode:
                shop.last_explained_barcode = barcode
                product = await lookup_barcode(barcode)
                if product:
                    shop.shopping_list.append(product["name"])
                    return {"action": "speak", "text": format_product_speech(product),
                            "state": "explaining"}

            # Barcode unreadable or already read — fall back to OCR
            ocr_text = read_text(frame)
            if ocr_text:
                return {"action": "speak",
                        "text": f"Packaging says: {ocr_text}",
                        "state": "explaining"}
            return {"action": "speak",
                    "text": f"You have the {shop.target_item}. "
                            "I couldn't read the label — try holding it steadier.",
                    "state": "explaining"}

        if now - shop.last_spoken_at >= _GUIDANCE_COOLDOWN:
            shop.last_spoken_at = now
            return {"action": "speak",
                    "text": _guidance(matched["bbox"], frame.shape, dist),
                    "state": "guiding"}
        return {"action": "idle"}

    elif shop.state == "explaining":
        # In explaining state keep scanning for barcodes;
        # once the user says "done" / "next" we return to scanning.
        barcode = scan_barcode(frame)
        if barcode and barcode != shop.last_explained_barcode:
            shop.last_explained_barcode = barcode
            product = await lookup_barcode(barcode)
            if product:
                shop.shopping_list.append(product["name"])
                return {"action": "speak", "text": format_product_speech(product),
                        "state": "explaining"}
        return {"action": "idle"}

    return {"action": "idle"}


# ── Per-frame dispatcher ──────────────────────────────────────────────────────

async def _process_frame(frame: np.ndarray, session: ClientSession) -> dict:
    now = time()

    if session.mode == "shopping":
        return await _process_shopping(frame, session.shopping)

    elif session.mode == "describe":
        if now - session.last_describe_time >= _DESCRIBE_INTERVAL:
            session.last_describe_time = now
            objects = yolo_service.detect_center_region(frame)
            return {"action": "describe", "objects": objects}
        return {"action": "idle"}

    else:  # navigation / collision-warning mode
        result = yolo_service.process_frame(frame)
        if result.alert_msg and (now - session.last_alert_time) >= _ALERT_COOLDOWN:
            session.last_alert_time = now
            return {"action": "speak", "text": result.alert_msg, "objects": result.objects}
        return {"action": "idle", "objects": result.objects}


# ── Command handler ───────────────────────────────────────────────────────────

async def _handle_command(cmd: str, session: ClientSession, ws: WebSocket) -> None:
    cmd = cmd.lower().strip()

    # ── Mode switches ──
    if cmd in ("mode:navigation", "mode:shopping", "mode:describe"):
        session.mode = cmd.split(":")[1]
        if session.mode == "shopping":
            session.shopping = ShoppingSession()
        await ws.send_text(json.dumps({
            "action": "speak",
            "text": f"Switched to {session.mode} mode.",
        }))

    # ── Shopping: pick an item ──
    elif cmd.startswith("pick:") or cmd.startswith("want:"):
        item = cmd.split(":", 1)[1].strip()
        session.shopping.target_item = item
        session.shopping.state = "guiding"
        session.shopping.last_spoken_at = 0.0
        await ws.send_text(json.dumps({
            "action": "speak",
            "text": f"Sure, guiding you to the {item}. Follow my directions.",
            "state": "guiding",
        }))

    # ── Shopping: done / next / cancel ──
    elif cmd in ("done", "next", "cancel"):
        session.shopping.state = "scanning"
        session.shopping.target_item = None
        session.shopping.target_bbox = None
        await ws.send_text(json.dumps({
            "action": "speak",
            "text": "Back to scanning. Point the camera at the shelf.",
            "state": "scanning",
        }))

    # ── Shopping: read list ──
    elif cmd == "list":
        items = session.shopping.shopping_list
        text = ("Your shopping list: " + ", ".join(items) + ".") if items \
            else "Your shopping list is empty."
        await ws.send_text(json.dumps({"action": "speak", "text": text}))


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@router.websocket("/ws/stream")
async def stream_endpoint(websocket: WebSocket):
    await websocket.accept()
    session = ClientSession()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if msg.get("type") == "command":
                await _handle_command(msg.get("cmd", ""), session, websocket)
                continue

            if msg.get("type") == "frame":
                frame_bytes = base64.b64decode(msg.get("data", ""))
                arr = np.frombuffer(frame_bytes, dtype=np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if frame is None:
                    continue
                response = await _process_frame(frame, session)
                await websocket.send_text(json.dumps(response))

    except WebSocketDisconnect:
        pass
