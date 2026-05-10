/**
 * camera.js — camera capture + WebSocket frame streaming
 *
 * Connects to /ws/stream, sends JPEG frames at TARGET_FPS,
 * and dispatches server responses to the rest of the app.
 */

import { speak, streamDescription } from "./voice.js";

const TARGET_FPS = 8;
const FRAME_INTERVAL = 1000 / TARGET_FPS;

let _ws = null;
let _stream = null;
let _intervalId = null;
let _canvas = null;
let _ctx = null;
let _video = null;

export function initCamera() {
  _video = document.getElementById("camera");
  _canvas = document.getElementById("capture");
  _ctx = _canvas.getContext("2d");
  _connectWS();
}

// ── WebSocket ─────────────────────────────────────────────────────────────────

function _connectWS() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  _ws = new WebSocket(`${proto}://${location.host}/ws/stream`);

  _ws.onopen = () => {
    console.log("[WS] connected");
    _startCamera();
  };

  _ws.onmessage = (event) => {
    let msg;
    try { msg = JSON.parse(event.data); } catch (_) { return; }
    _handleServerMessage(msg);
  };

  _ws.onclose = () => {
    console.warn("[WS] disconnected — reconnecting in 2s");
    clearInterval(_intervalId);
    setTimeout(_connectWS, 2000);
  };

  _ws.onerror = (e) => console.error("[WS error]", e);
}

// ── Camera + frame capture ────────────────────────────────────────────────────

async function _startCamera() {
  try {
    _stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: 640, height: 480 },
      audio: false,
    });
    _video.srcObject = _stream;
    await _video.play();
    _canvas.width = 640;
    _canvas.height = 480;
    _intervalId = setInterval(_sendFrame, FRAME_INTERVAL);
  } catch (err) {
    speak("Camera access denied. Please allow camera permissions and refresh.");
    console.error("[Camera]", err);
  }
}

function _sendFrame() {
  if (!_ws || _ws.readyState !== WebSocket.OPEN) return;
  if (!_video.videoWidth) return;

  _ctx.drawImage(_video, 0, 0, _canvas.width, _canvas.height);
  const dataUrl = _canvas.toDataURL("image/jpeg", 0.7);
  const b64 = dataUrl.split(",")[1];
  _ws.send(JSON.stringify({ type: "frame", data: b64 }));
}

// ── Server message dispatcher ─────────────────────────────────────────────────

function _handleServerMessage(msg) {
  switch (msg.action) {
    case "speak":
      speak(msg.text);
      _updateShopStatus(msg);
      break;

    case "describe":
      // Objects from YOLO — kick off SSE description stream
      streamDescription(msg.objects || []);
      break;

    case "idle":
      break;
  }
}

function _updateShopStatus(msg) {
  const el = document.getElementById("shop-status");
  if (!el || !msg.state) return;
  const labels = { scanning: "Scanning...", guiding: "Guiding...", explaining: "Reading item..." };
  el.textContent = labels[msg.state] || "";
}

// ── Public: send command to server ───────────────────────────────────────────

export function sendCommand(cmd) {
  if (_ws && _ws.readyState === WebSocket.OPEN) {
    _ws.send(JSON.stringify({ type: "command", cmd }));
  }
}
