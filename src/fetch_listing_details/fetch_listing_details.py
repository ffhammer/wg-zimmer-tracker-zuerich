import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from src.fetch_listing_details.commute_data import fetch_bike_connection, fetch_journey
from src.fetch_listing_details.fetch_location import fetch_location
from src.fetch_listing_lists.ListingScraped import ListingScraped
from src.logger import logger
from src.models import (
    ListingStored,
)

assert load_dotenv()


def chunked(lst: list, n: int) -> list[list]:
    return [lst[i : i + n] for i in range(0, len(lst), n)]


def batch_create_listing_stored(
    inputs: list[tuple[ListingScraped, datetime]],
    max_requests_per_minute: int = 40,
    max_requests_per_second: int = 2,
) -> list[ListingStored]:
    outputs: dict[str, ListingStored] = {}

    # split into minute-batches
    for minute_batch in chunked(inputs, max_requests_per_minute):
        # split each minute into second-batches
        minute_start = time.time()

        for sec_batch in chunked(minute_batch, max_requests_per_second):
            start = time.time()
            with ThreadPoolExecutor(max_workers=len(sec_batch)) as executor:
                results = list(
                    executor.map(lambda args: create_listing_stored(*args), sec_batch)
                )
            for lst in results:
                outputs[str(lst.url)] = lst
            # throttle to one second per sub-batch
            elapsed = time.time() - start
            if elapsed < 1.0:
                time.sleep(1.0 - elapsed)

        elapsed = time.time() - minute_start
        if elapsed < 60.0:
            time.sleep(60.0 - elapsed)
    # preserve original order
    return [outputs[str(scr.url)] for scr, _ in inputs]


def create_listing_stored(scraped: ListingScraped, now: datetime) -> ListingStored:
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

    listing.latitude, listing.longitude = fetch_location(listing)

    if listing.latitude and listing.longitude:
        listing.public_transport = fetch_journey(
            from_lat=listing.latitude, from_lon=listing.longitude
        )
        listing.bike = fetch_bike_connection(
            from_lat=listing.latitude, from_lon=listing.longitude
        )

    return listing
