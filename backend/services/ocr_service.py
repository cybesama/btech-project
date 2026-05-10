from typing import Optional

import cv2
import numpy as np

_easyocr_reader = None


def _get_reader():
    global _easyocr_reader
    if _easyocr_reader is None:
        import easyocr
        _easyocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _easyocr_reader


def scan_barcode(frame: np.ndarray) -> Optional[str]:
    """Return the first barcode/QR value found in frame, or None."""
    from pyzbar.pyzbar import decode as pyzbar_decode
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    codes = pyzbar_decode(gray)
    if codes:
        return codes[0].data.decode("utf-8")
    return None


def read_text(frame: np.ndarray) -> str:
    """Extract visible text from frame using EasyOCR."""
    reader = _get_reader()
    results = reader.readtext(frame, detail=0, paragraph=True)
    return " ".join(results).strip()
