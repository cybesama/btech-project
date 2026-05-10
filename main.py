import cv2
import numpy as np
from time import time
import pyttsx3
import queue
import threading
import zmq

from util.obj_detection import objectDetection
from util.vis import visualize_frame
from util.distance_est import calculate_distance
from util.create_bounding_box import ego_roi
from logical.warning import collision_warning

# --- ZMQ subscriber ---
context = zmq.Context()
socket  = context.socket(zmq.SUB)
socket.connect('tcp://127.0.0.1:5555')
socket.setsockopt_string(zmq.SUBSCRIBE, '')

# --- Object detector ---
detect = objectDetection()

# --- Non-blocking voice assistant ---
# maxsize=1 ensures stale alerts are dropped rather than queued
_voice_queue = queue.Queue(maxsize=1)

def _voice_worker():
    engine = pyttsx3.init()
    voices = engine.getProperty('voices')
    if len(voices) > 1:
        engine.setProperty('voice', voices[1].id)
    while True:
        text = _voice_queue.get()
        if text is None:
            break
        engine.say(text)
        engine.runAndWait()

_voice_thread = threading.Thread(target=_voice_worker, daemon=True)
_voice_thread.start()

def run_voiceAssist(text):
    try:
        _voice_queue.put_nowait(text)
    except queue.Full:
        pass  # drop if the previous alert is still being spoken

# --- Alert cooldown (seconds) ---
ALERT_COOLDOWN  = 3.0
last_alert_time = 0.0

# --- Main loop ---
while True:
    try:
        message = socket.recv_pyobj()
        frame   = cv2.imdecode(message['shreasi'], cv2.IMREAD_COLOR)
        if frame is None:
            print("[Warning] Received empty frame. Skipping...")
            continue

        frame_width = frame.shape[1]
        start_time  = time()

        name, box_coord, obj_detected_frame = detect.detect_objects(frame)

        DIST_H_per_FRAME, DIST_2_per_FRAME, frame_2, box_coord_2, name_2 = \
            calculate_distance(box_coord, obj_detected_frame, name)

        frame_3_roi, coords_in_roi, distance_in_roi, names_in_roi = \
            ego_roi(frame_2, name_2, box_coord_2, DIST_H_per_FRAME)

        alert_msg = collision_warning(
            coords_in_roi, distance_in_roi, names_in_roi, frame_3_roi, frame_width
        )

        now = time()
        if alert_msg and (now - last_alert_time) >= ALERT_COOLDOWN:
            run_voiceAssist(alert_msg)
            last_alert_time = now
            print(f"[Alert] {alert_msg}")

        end_time = time()
        visualize_frame(obj_detected_frame, start_time, end_time)

    except Exception as e:
        print(f"[Error] {e}")
