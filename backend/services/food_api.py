from typing import Optional

import httpx

_OFF_URL = "https://world.openfoodfacts.org/api/v0/product/{barcode}.json"


async def lookup_barcode(barcode: str) -> Optional[dict]:
    """Fetch product info from Open Food Facts. Returns None if not found."""
    url = _OFF_URL.format(barcode=barcode)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers={"User-Agent": "BlindGuidanceSystem/1.0"})
        data = resp.json()
    except Exception:
        return None

    if data.get("status") != 1:
        return None

    p = data["product"]
    nutriments = p.get("nutriments", {})

    return {
        "name": p.get("product_name") or p.get("product_name_en", "Unknown product"),
        "brand": p.get("brands", ""),
        "quantity": p.get("quantity", ""),
        "ingredients": (p.get("ingredients_text_en") or p.get("ingredients_text", ""))[:250],
        "allergens": [a.replace("en:", "") for a in p.get("allergens_tags", [])],
        "calories_per_100g": nutriments.get("energy-kcal_100g"),
        "fat_per_100g": nutriments.get("fat_100g"),
        "carbs_per_100g": nutriments.get("carbohydrates_100g"),
        "protein_per_100g": nutriments.get("proteins_100g"),
    }


def format_product_speech(product: dict) -> str:
    """Convert a product dict into a natural-sounding spoken sentence."""
    name = product["name"]
    brand = product["brand"]

    intro = f"This is {name} by {brand}" if brand else f"This is {name}"
    if product["quantity"]:
        intro += f", {product['quantity']}"
    parts = [intro + "."]

    if product["allergens"]:
        allergens = " and ".join(product["allergens"])
        parts.append(f"Contains {allergens}.")

    nutrition = []
    if product["calories_per_100g"]:
        nutrition.append(f"{int(product['calories_per_100g'])} calories")
    if product["fat_per_100g"] is not None:
        nutrition.append(f"{product['fat_per_100g']:.1f}g fat")
    if product["carbs_per_100g"] is not None:
        nutrition.append(f"{product['carbs_per_100g']:.1f}g carbs")
    if product["protein_per_100g"] is not None:
        nutrition.append(f"{product['protein_per_100g']:.1f}g protein")
    if nutrition:
        parts.append(f"Per 100 grams: {', '.join(nutrition)}.")

    return " ".join(parts)
