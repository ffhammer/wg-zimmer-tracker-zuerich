from src.logger import logger
from src.models import ListingStored


import requests


import os


def fetch_location(listing: ListingStored) -> tuple[None, None] | tuple[float, float]:
    """Return (lat, lon) if correct else (None, None) and logs error"""
    ordered_atrs = [listing.adresse, listing.ort, listing.region]
    if not all(ordered_atrs):
        return None, None

    address = ", ".join(ordered_atrs + ["Switzerland"])
    api_key = os.environ.get("LOCATIONIQ_API_KEY")
    if not api_key:
        logger.error("LOCATIONIQ_API_KEY not set in environment")
        return None, None

    params = {
        "key": api_key,
        "q": address,
        "format": "json",
        "limit": 1,
    }

    try:
        resp = requests.get(
            "https://us1.locationiq.com/v1/search.php", params=params, timeout=5
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            logger.error(
                f"No results from LocationIQ for '{address}' (url: {listing.url})"
            )
            return None, None

        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
        logger.debug(f"Successfully fetched location for '{address}': ({lat}, {lon})")
        return lat, lon

    except Exception as e:
        logger.error(
            f"Could not fetch location for '{address}'. error: {e}. url '{listing.url}'"
        )
        return None, None
