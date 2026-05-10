import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.config import config
from backend.db.database import init_db
from backend.routes import describe, emergency, navigation, poi, stream

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Pre-load YOLO at startup so the first request isn't slow
    from backend.services.yolo_service import yolo_service  # noqa: F401
    yield


app = FastAPI(title="Blind Guidance System", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API routes (must be registered before the static-file catch-all) ─────────
app.include_router(stream.router)
app.include_router(navigation.router)
app.include_router(poi.router)
app.include_router(describe.router)
app.include_router(emergency.router)


@app.get("/api/config")
async def get_config():
    return JSONResponse({"status": "ok"})


# ── Frontend static files ─────────────────────────────────────────────────────
_frontend = os.path.join(_PROJECT_ROOT, "frontend")
if os.path.exists(_frontend):
    app.mount("/", StaticFiles(directory=_frontend, html=True), name="frontend")
