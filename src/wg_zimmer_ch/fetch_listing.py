import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from src.geo.fetch_location import fetch_cordinates
from src.logger import logger
from src.models import (
    WGZimmerCHListing,
)
from src.wg_zimmer_ch.fetch_lists.ListingScraped import ListingScraped

assert load_dotenv()


def create_listing_stored(scraped: ListingScraped, now: datetime) -> WGZimmerCHListing:
    listing = WGZimmerCHListing(
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


def extract_atributes(listing: WGZimmerCHListing, response) -> WGZimmerCHListing:
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

    base_url = "https://www.wgzimmer.ch"
    listing.img_urls = list(
        {
            tag["content"]
            for tag in soup.find_all("meta", {"property": "og:image"})
            if tag.get("content")
        }.union(
            {
                base_url + img["src"]
                for img in soup.find_all("img")
                if img.get("src") and img["src"].startswith("/docroot/img.wgzimmer.ch")
            }
        ).difference(("https://www.wgzimmer.ch/docroot/img.wgzimmer.ch/loading.gif",))
    )

    match = re.search(
        r"ol\.proj\.fromLonLat\(\[\s*([+-]?\d+\.\d+)\s*,\s*([+-]?\d+\.\d+)\s*\]\)",
        response.content,
    )
    if match:
        listing.longitude, listing.latitude = (
            float(match.group(1)),
            float(match.group(2)),
        )
    else:
        logger.info(
            "could not fetch longitude and langitude from the map. using the api"
        )
        listing.latitude, listing.longitude = fetch_cordinates(listing)

    return listing
