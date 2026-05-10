from fastapi import APIRouter, HTTPException

from backend.services.maps_service import POI_CATEGORIES, get_nearby_pois

router = APIRouter(prefix="/poi", tags=["poi"])


@router.get("/nearby")
async def nearby_pois(lat: float, lng: float, category: str, radius: int = 1000):
    if category not in POI_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown category. Valid: {list(POI_CATEGORIES.keys())}",
        )

    places = await get_nearby_pois(lat, lng, category, radius)

    if not places:
        return {
            "speech": f"No {category} found within {radius} meters.",
            "places": [],
        }

    closest = places[0]
    speech = (
        f"Nearest {category}: {closest['name']}, "
        f"{closest['distance_m']} meters {closest['direction']}."
    )
    if len(places) > 1:
        speech += (
            f" Also nearby: {places[1]['name']} "
            f"at {places[1]['distance_m']} meters {places[1]['direction']}."
        )

    return {"speech": speech, "places": places}
