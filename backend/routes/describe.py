import json
from typing import List

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.services.llm_service import describe_scene_stream

router = APIRouter(prefix="/describe", tags=["describe"])


class DescribeRequest(BaseModel):
    objects: List[dict]


@router.post("/stream")
async def stream_description(req: DescribeRequest):
    """SSE endpoint — streams Ollama tokens as server-sent events."""

    async def event_gen():
        async for token in describe_scene_stream(req.objects):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
