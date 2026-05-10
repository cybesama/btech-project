import cv2
import numpy as np

COLLISION_THRESHOLD = 3.0   # metres — objects closer than this trigger an alert
URGENT_THRESHOLD    = 1.5   # metres — closer than this → urgent wording


def get_alert_message(coords_in_roi, distance_in_roi, names_in_roi, frame_width):
    """Return a spoken alert string for the closest in-path obstacle, or None."""
    if not distance_in_roi:
        return None

    min_idx = min(range(len(distance_in_roi)), key=lambda i: distance_in_roi[i])
    dist    = distance_in_roi[min_idx]

    if dist >= COLLISION_THRESHOLD:
        return None

    coord        = coords_in_roi[min_idx]
    object_name  = names_in_roi[min_idx] if min_idx < len(names_in_roi) else "obstacle"
    obj_center_x = (coord[0] + coord[2]) // 2

    left_boundary  = frame_width // 3
    right_boundary = (frame_width * 2) // 3

    if obj_center_x < left_boundary:
        direction  = "on your left"
        suggestion = "move right"
    elif obj_center_x > right_boundary:
        direction  = "on your right"
        suggestion = "move left"
    else:
        direction  = "directly ahead"
        suggestion = "stop"

    if dist < URGENT_THRESHOLD:
        return f"Warning! {object_name} {direction}. {suggestion} immediately."
    else:
        return f"Caution. {object_name} {direction} at {dist:.1f} meters. {suggestion}."


def collision_warning(coords_in_roi, distance_in_roi, names_in_roi, frame_3_roi, frame_width):
    """Draw collision indicators on the frame and return the alert message string."""
    alert_msg = get_alert_message(coords_in_roi, distance_in_roi, names_in_roi, frame_width)

    for i in range(len(coords_in_roi)):
        if distance_in_roi[i] < COLLISION_THRESHOLD:
            RED = (0, 0, 255)
            x1, y1, x2, y2 = coords_in_roi[i]
            cv2.rectangle(frame_3_roi, (x1, y1), (x2, y2), RED, 3)
            cv2.putText(frame_3_roi, f"{distance_in_roi[i]:.1f}m", (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, RED, 2)

    if alert_msg:
        cv2.putText(frame_3_roi, "!! COLLISION DETECTED !!", (80, 120),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 4)

    return alert_msg
