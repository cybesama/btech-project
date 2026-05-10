import base64
import json
from typing import AsyncGenerator, List, Optional

import cv2
import httpx
import numpy as np

from backend.config import config


def _fmt_obj(o: dict) -> str:
    dist = f"{o['distance']:.1f}m" if o.get("distance") else "unknown distance"
    return f"{o['name']} ({o.get('zone', 'ahead')}, {dist})"


async def describe_scene_stream(
    objects: List[dict],
    frame: Optional[np.ndarray] = None,
) -> AsyncGenerator[str, None]:
    """Stream an AI description of the current scene from Ollama."""

    obj_desc = ", ".join(_fmt_obj(o) for o in objects) if objects else "nothing specific"

    prompt = (
        "You are describing a scene to a blind person as a warm, observant friend. "
        f"Objects detected: {obj_desc}. "
        "In 2–3 natural, vivid sentences, describe what this environment looks and feels like. "
        "Be descriptive but practical. Never use technical words like 'bounding box' or 'detected'."
    )

    payload: dict = {
        "model": config.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": True,
    }

    if frame is not None:
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        payload["images"] = [base64.b64encode(buf.tobytes()).decode()]

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST", f"{config.OLLAMA_HOST}/api/generate", json=payload
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        token = data.get("response", "")
                        if token:
                            yield token
                        if data.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue
    except Exception as exc:
        yield f"Scene description unavailable: {exc}"
