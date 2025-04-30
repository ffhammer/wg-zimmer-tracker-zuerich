from logger import logger
from models import ListingScraped, ListingStored
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from geopy.geocoders import OpenCage
from dotenv import load_dotenv
import os

assert load_dotenv()


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


def create_listing_stored(scraped: ListingStored, now: datetime) -> ListingScraped:

    listing = ListingStored(
        **scraped.model_dump(exclude_none=True),
        first_seen=now,
        last_seen=now,
    )
    logger.debug(f"Fetching: {listing.url}")
    response = requests.get(listing.url)

    if not response.ok:
        logger.error(f"Failed fetching {listing.url} - {response.status_code}")
        return listing

    try:
        return extract_atributes(listing, response)
    except Exception as e:
        logger.error(f"extract_atributes failed with '{e}' for:\n{listing.url}")

    return listing


def extract_atributes(listing, response):
    soup = BeautifulSoup(response.content, "html.parser")

    address_div = soup.select_one("div.adress-region")
    if address_div:

        def extract_nested_value(name: str) -> str | None:
            try:
                val = address_div.find("strong", string=name)
                return val.next_sibling.strip() if val and val.next_sibling else None
            except Exception as e:
                logger.error(f"extracting {name} failed with {e}")

        listing.region = extract_nested_value("Region")
        listing.adresse = extract_nested_value("Adresse")
        listing.ort = extract_nested_value("Ort")

    def extract_simple_value(query: str) -> str | None:
        try:
            res = soup.select_one(query)

            return res.get_text(separator=" ", strip=True) if res else None
        except Exception as e:
            logger.error(f"extracting {query} failed with {e}")

    listing.beschreibung = extract_simple_value("div.mate-content > p")
    listing.wir_suchen = extract_simple_value("div.room-content > p")
    listing.wir_sind = extract_simple_value("div.person-content > p")

    listing.latitude, listing.longitude = fetch_location(listing)

    return listing
