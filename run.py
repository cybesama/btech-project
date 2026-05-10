import sys
import os

# Add project root to path so backend/, util/, logical/ are all importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Disable Ultralytics auto-update (avoids pip marker crash on Python 3.9)
os.environ.setdefault("YOLO_AUTOINSTALL", "False")
os.environ.setdefault("ULTRALYTICS_AUTO_UPDATE", "0")

import uvicorn

if __name__ == "__main__":
    uvicorn.run("backend.app:app", host="0.0.0.0", port=8000, reload=True)
