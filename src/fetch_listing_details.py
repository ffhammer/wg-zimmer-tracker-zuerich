import logging
from models import ListingScraped, ListingStored
import requests
from bs4 import BeautifulSoup
from datetime import datetime


def create_listing_stored(scraped: ListingStored, now: datetime) -> ListingScraped:

    listing = ListingStored(
        **scraped.model_dump(exclude_none=True),
        first_seen=now,
        last_seen=now,
    )
    logging.debug(f"Fetching: {listing.url}")
    response = requests.get(listing.url)

    if not response.ok:
        logging.error(f"Failed fetching {listing.url} - {response.status_code}")
        return listing

    try:
        return extract_atributes(listing, response)
    except Exception as e:
        logging.error(f"extract_atributes failed with '{e}' for:\n{listing.url}")

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
                logging.error(f"extracting {name} failed with {e}")

        listing.region = extract_nested_value("Region")
        listing.adresse = extract_nested_value("Adresse")
        listing.ort = extract_nested_value("Ort")

    def extract_simple_value(query: str) -> str | None:
        try:
            res = soup.select_one(query)

            return res.get_text(separator=" ", strip=True) if res else None
        except Exception as e:
            logging.error(f"extracting {query} failed with {e}")

    listing.beschreibung = extract_simple_value("div.mate-content > p")
    listing.wir_suchen = extract_simple_value("div.room-content > p")
    listing.wir_sind = extract_simple_value("div.person-content > p")

    return listing
