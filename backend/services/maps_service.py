import math
import re
from typing import List, Optional, Tuple

import httpx

_PHOTON_URL   = "https://photon.komoot.io/api/"
_OSRM_URL     = "http://router.project-osrm.org/route/v1/foot"   # HTTP: avoids macOS Python 3.9 TLS issue
_OVERPASS_URL = "https://overpass-api.de/api/interpreter"

_HEADERS  = {"User-Agent": "BlindGuidanceSystem/1.0"}
_HTTP_CFG = {"headers": _HEADERS, "verify": False, "timeout": 12.0}

POI_CATEGORIES = {
    "hospital":    '["amenity"="hospital"]',
    "clinic":      '["amenity"="clinic"]',
    "pharmacy":    '["amenity"="pharmacy"]',
    "supermarket": '["shop"="supermarket"]',
    "grocery":     '["shop"~"grocery|convenience"]',
    "dentist":     '["amenity"="dentist"]',
    "barber":      '["shop"="hairdresser"]',
    "police":      '["amenity"="police"]',
    "bank":        '["amenity"="bank"]',
    "atm":         '["amenity"="atm"]',
}

_CARDINALS = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"]


# ── Geocode ────────────────────────────────────────────────────────────────────

async def geocode(place_name: str) -> Optional[Tuple[float, float]]:
    """Geocode using Photon (OSM-based, no key, no rate-limit restrictions)."""
    try:
        async with httpx.AsyncClient(**_HTTP_CFG) as client:
            resp = await client.get(_PHOTON_URL, params={"q": place_name, "limit": 1})
        if resp.status_code != 200 or not resp.text.strip():
            return None
        data = resp.json()
        features = data.get("features", [])
        if not features:
            return None
        coords = features[0]["geometry"]["coordinates"]  # [lng, lat]
        return float(coords[1]), float(coords[0])
    except Exception:
        return None


# ── Route planning ─────────────────────────────────────────────────────────────

async def get_route(origin_lat: float, origin_lng: float, destination: str) -> dict:
    coords = await geocode(destination)
    if not coords:
        return {"error": "Destination not found"}

    dest_lat, dest_lng = coords

    url = f"{_OSRM_URL}/{origin_lng},{origin_lat};{dest_lng},{dest_lat}"
    async with httpx.AsyncClient(**_HTTP_CFG) as client:
        resp = await client.get(url, params={
            "steps": "true", "geometries": "geojson", "overview": "full",
        })
    if resp.status_code != 200 or not resp.text.strip():
        return {"error": "Routing service unavailable"}
    try:
        data = resp.json()
    except Exception:
        return {"error": "Bad response from routing service"}

    if data.get("code") != "Ok" or not data.get("routes"):
        return {"error": "Route not found"}

    route  = data["routes"][0]
    leg    = route["legs"][0]
    total_m = route["distance"]
    total_s = route["duration"]

    steps = []
    for s in leg["steps"]:
        maneuver = s.get("maneuver", {})
        instruction = _osrm_instruction(maneuver, s.get("name", ""))
        loc = maneuver.get("location", [dest_lng, dest_lat])
        steps.append({
            "instruction": instruction,
            "distance_m":  s["distance"],
            "end_lat":     loc[1],
            "end_lng":     loc[0],
        })

    dist_text = f"{int(total_m)} meters" if total_m < 1000 else f"{total_m/1000:.1f} km"
    dur_text  = f"{int(total_s // 60)} min"

    return {
        "total_distance": dist_text,
        "total_duration": dur_text,
        "steps":    steps,
        "end_lat":  dest_lat,
        "end_lng":  dest_lng,
        "geometry": route.get("geometry"),
    }


def _osrm_instruction(maneuver: dict, road_name: str) -> str:
    mtype  = maneuver.get("type", "")
    mod    = maneuver.get("modifier", "")
    road   = f" onto {road_name}" if road_name else ""
    if mtype == "depart":
        return f"Head {mod or 'forward'}{road}"
    if mtype == "arrive":
        return "You have arrived at your destination"
    if mtype == "turn":
        return f"Turn {mod}{road}"
    if mtype == "continue":
        return f"Continue straight{road}"
    if mtype == "roundabout":
        exit_n = maneuver.get("exit", "")
        return f"At the roundabout, take exit {exit_n}{road}"
    return f"{mtype.replace('-', ' ').capitalize()}{road}"


def navigation_guidance(
    current_lat: float, current_lng: float, steps: List[dict]
) -> Tuple[str, int]:
    for i, step in enumerate(steps):
        dist = _haversine(current_lat, current_lng, step["end_lat"], step["end_lng"])
        if dist > 15:
            dist_text = (
                f"{int(dist)} meters" if dist < 1000 else f"{dist/1000:.1f} kilometers"
            )
            return f"In {dist_text}, {step['instruction']}.", i
    return "You have arrived at your destination.", len(steps) - 1


# ── Nearby POI via Overpass ────────────────────────────────────────────────────

async def get_nearby_pois(
    lat: float, lng: float, category: str, radius: int = 1000
) -> List[dict]:
    tag_filter = POI_CATEGORIES.get(category, f'["amenity"="{category}"]')
    query = (
        f"[out:json][timeout:10];"
        f"(node{tag_filter}(around:{radius},{lat},{lng});"
        f"way{tag_filter}(around:{radius},{lat},{lng}););"
        f"out center 5;"
    )
    async with httpx.AsyncClient(**_HTTP_CFG) as client:
        resp = await client.post(_OVERPASS_URL, data={"data": query})
    data = resp.json()

    results = []
    for elem in data.get("elements", [])[:5]:
        plat = elem.get("lat") or elem.get("center", {}).get("lat")
        plng = elem.get("lon") or elem.get("center", {}).get("lon")
        if plat is None:
            continue
        name = elem.get("tags", {}).get("name") or category.capitalize()
        dist = _haversine(lat, lng, plat, plng)
        direction = _cardinal(_bearing(lat, lng, plat, plng))
        results.append({
            "name":       name,
            "distance_m": int(dist),
            "direction":  direction,
        })

    results.sort(key=lambda x: x["distance_m"])
    return results


# ── Geometry helpers ───────────────────────────────────────────────────────────

def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _bearing(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    lat1, lat2 = math.radians(lat1), math.radians(lat2)
    dlng = math.radians(lng2 - lng1)
    x = math.sin(dlng) * math.cos(lat2)
    y = math.cos(lat1)*math.sin(lat2) - math.sin(lat1)*math.cos(lat2)*math.cos(dlng)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _cardinal(bearing: float) -> str:
    return _CARDINALS[round(bearing / 45) % 8]
