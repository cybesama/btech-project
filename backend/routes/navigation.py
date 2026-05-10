from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.db.models import SavedRoute
from backend.services.maps_service import get_route, navigation_guidance

router = APIRouter(prefix="/navigate", tags=["navigation"])


class RouteRequest(BaseModel):
    origin_lat: float
    origin_lng: float
    destination: str


class PositionUpdate(BaseModel):
    lat: float
    lng: float
    steps: List[dict]


class SaveRouteRequest(BaseModel):
    name: str
    destination_name: str
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float


@router.post("/route")
async def start_navigation(req: RouteRequest):
    result = await get_route(req.origin_lat, req.origin_lng, req.destination)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/position")
async def update_position(req: PositionUpdate):
    guidance, step_idx = navigation_guidance(req.lat, req.lng, req.steps)
    return {"guidance": guidance, "step_index": step_idx}


@router.post("/save")
async def save_route(req: SaveRouteRequest, db: Session = Depends(get_db)):
    existing = db.query(SavedRoute).filter(
        SavedRoute.destination_name == req.destination_name
    ).first()
    if existing:
        existing.use_count += 1
        existing.last_used = datetime.utcnow()
        db.commit()
        return {"id": existing.id, "message": "Route use count updated"}

    route = SavedRoute(**req.dict())
    db.add(route)
    db.commit()
    db.refresh(route)
    return {"id": route.id, "message": "Route saved"}


@router.get("/saved")
async def list_saved_routes(db: Session = Depends(get_db)):
    routes = (
        db.query(SavedRoute)
        .order_by(SavedRoute.use_count.desc())
        .limit(10)
        .all()
    )
    return [
        {
            "id": r.id,
            "name": r.name,
            "destination_name": r.destination_name,
            "use_count": r.use_count,
            "start": {"lat": r.start_lat, "lng": r.start_lng},
            "end": {"lat": r.end_lat, "lng": r.end_lng},
        }
        for r in routes
    ]


@router.delete("/saved/{route_id}")
async def delete_route(route_id: int, db: Session = Depends(get_db)):
    route = db.query(SavedRoute).filter(SavedRoute.id == route_id).first()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    db.delete(route)
    db.commit()
    return {"message": "Route deleted"}
