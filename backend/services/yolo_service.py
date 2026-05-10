from typing import List, Optional
from dataclasses import dataclass, field
import numpy as np

from util.obj_detection import objectDetection
from util.distance_est import calculate_distance
from util.create_bounding_box import ego_roi
from logical.warning import get_alert_message


@dataclass
class DetectionResult:
    alert_msg: Optional[str]
    objects: List[dict]      # [{name, bbox, distance}]
    annotated_frame: np.ndarray


class YOLOService:
    """Singleton wrapper around the existing YOLO + distance + ROI pipeline."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._detector = objectDetection()
        self._initialized = True

    # ── Navigation / collision mode ───────────────────────────────────────────

    def process_frame(self, frame: np.ndarray) -> DetectionResult:
        frame_width = frame.shape[1]
        name, box_coord, detected_frame = self._detector.detect_objects(frame)
        dist_h, _, frame2, box2, name2 = calculate_distance(box_coord, detected_frame, name)
        frame3, coords_roi, dist_roi, names_roi = ego_roi(frame2, name2, box2, dist_h)
        alert = get_alert_message(coords_roi, dist_roi, names_roi, frame_width)

        objects = [
            {
                "name": names_roi[i],
                "bbox": coords_roi[i],
                "distance": dist_roi[i] if i < len(dist_roi) else None,
            }
            for i in range(len(names_roi))
        ]
        return DetectionResult(alert_msg=alert, objects=objects, annotated_frame=frame3)

    # ── Shopping mode ─────────────────────────────────────────────────────────

    def detect_center_region(self, frame: np.ndarray) -> List[dict]:
        """Detect objects inside the center 50% × 60% crop for shopping mode."""
        h, w = frame.shape[:2]
        x1, x2 = w // 4, (w * 3) // 4
        y1, y2 = h // 5, (h * 4) // 5
        crop = frame[y1:y2, x1:x2]

        name, box_coord, _ = self._detector.detect_objects(crop)
        dist_h, _, _, box2, name2 = calculate_distance(box_coord, crop, name)

        crop_w = x2 - x1
        results = []
        for i, (n, box) in enumerate(zip(name2, box2)):
            cx = (box[0] + box[2]) // 2
            if cx < crop_w // 3:
                zone = "left"
            elif cx > (crop_w * 2) // 3:
                zone = "right"
            else:
                zone = "center"

            # Re-map bbox coords back to full-frame coordinates
            full_bbox = [box[0] + x1, box[1] + y1, box[2] + x1, box[3] + y1]
            results.append({
                "name": n,
                "bbox": full_bbox,
                "distance": dist_h[i] if i < len(dist_h) else None,
                "zone": zone,
            })

        return results


yolo_service = YOLOService()
