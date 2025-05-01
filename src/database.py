# database.py
import os
from datetime import datetime
from typing import List, Literal, Optional, Tuple

from pydantic import HttpUrl
from tinydb import Query, TinyDB
from tinydb.operations import set as tinyset

from src import students_ch, wg_zimmer_ch, woko
from src.geo.commutes import batch_fetch_commutes
from src.logger import logger
from src.models import (
    WEBSITE_TO_MODEL,
    BaseListing,
    DataBaseUpdate,
    StudentsCHListing,
    Webiste,
    WGZimmerCHListing,
    WokoListing,
)

DB_FILE = os.path.join("db.json")
MAX_GEO_REQEUSTS_PER_MINUTE = 33

db = TinyDB(DB_FILE, indent=4, ensure_ascii=False)
listings_table = db.table("listings")
updates_date = db.table("updates")
ListingQuery = Query()


def to_json_serialiable(dic: dict) -> dict:
    for key, val in dic.items():
        if isinstance(val, datetime):
            dic[key] = val.isoformat()
        if isinstance(val, HttpUrl):
            dic[key] = str(val)

    return dic


def get_listing_by_url(url: str) -> Optional[BaseListing]:
    """Holt ein spezifisches Listing anhand seiner URL."""
    result = listings_table.get(ListingQuery.url == url)
    if result:
        try:
            # Manually handle potential type errors during conversion
            return BaseListing(**result)
        except Exception as e:
            logger.error(
                f"Failed to parse listing from DB for URL {url}: {e}. Data: {result}"
            )
            return None
    return None


def upsert_listings(
    urls: List[HttpUrl],
    now: datetime,
    website: Webiste,
) -> Tuple[int, int]:
    """Fügt neue Listings hinzu oder aktualisiert bestehende.

    Returns:
        Tuple[int, int]: Anzahl neuer Listings, Anzahl aktualisierter Listings.
    """
    updated_count = 0

    insert_urls = []

    for url in urls:
        existing_doc = listings_table.get(ListingQuery.url == str(url))
        if existing_doc:
            model = load_correct(existing_doc)
            model.update(now)
            existing_doc.update(model.dump_json_serializable())
        else:
            insert_urls.append(url)

    new_count = insert(insert_urls, now, website)

    return new_count, updated_count


def insert(urls: list[HttpUrl], now: datetime, website: Webiste):
    function_dict = {
        Webiste.students_ch: students_ch.fetch_listings,
        Webiste.woko: woko.fetch_listings,
        Webiste.wg_zimmer_ch: wg_zimmer_ch.fetch_listings,
    }

    try:
        listings = function_dict[website](urls=urls, now=now)
        logger.debug(f"fetched {len(urls)} pages for {website}")
        listings = batch_fetch_commutes(
            listings, max_requests_per_minute=MAX_GEO_REQEUSTS_PER_MINUTE
        )
        logger.debug(f"fetched {len(urls)} commutes  for {website}")

        for listing in listings:
            listings_table.insert(listing.dump_json_serializable())
        return len(listings)
    except Exception as e:
        logger.exception(f"Error inserting new listing failed: {e}.")

    return False


def load_correct(jsons: str) -> WGZimmerCHListing | StudentsCHListing | WokoListing:
    return WEBSITE_TO_MODEL[jsons["website"]].model_validate(jsons)


def update(scraped, url_str, existing_doc, now):
    try:
        existing_listing = BaseListing(**existing_doc)
        existing_listing.update_from_scraped(scraped, now)
        return True
    except Exception as e:
        logger.error(f"Error updating listing {url_str}: {e}. Data: {existing_doc}")
    return False


def mark_listings_as_deleted(urls: list[HttpUrl], website: Webiste) -> int:
    """Markiert Listings in der DB als 'deleted', wenn sie nicht im letzten Fetch waren."""

    active_urls_in_fetch = {str(url) for url in urls}

    deleted_count = 0
    active_listings_in_db = listings_table.search(
        ListingQuery.status == "active" and ListingQuery.website == website
    )
    for listing_doc in active_listings_in_db:
        if listing_doc.get("url") not in active_urls_in_fetch:
            try:
                listings_table.update(
                    tinyset("status", "deleted"), ListingQuery.url == listing_doc["url"]
                )
                deleted_count += 1
                logger.debug(f"Marked listing as deleted: {listing_doc['url']}")
            except Exception as e:
                logger.error(
                    f"Error marking listing as deleted {listing_doc.get('url')}: {e}"
                )

    return deleted_count


def get_all_listings_stored(include_deleted=False) -> List[BaseListing]:
    """Holt alle Listings aus der DB."""
    if include_deleted:
        results = listings_table.all()
    else:
        results = listings_table.search(ListingQuery.status == "active")

    return [load_correct(doc) for doc in results]


def update_listing_user_status(
    url: str, field: Literal["gesehen", "gemerkt"], value: bool
) -> bool:
    """Aktualisiert den 'gesehen' oder 'gemerkt' Status eines Listings."""
    logger.debug(f"Updating DB: set {field}={value} for url={url}")
    try:
        listings_table.update({field: value}, ListingQuery.url == url)
    except Exception as e:
        logger.error(f"Error updating user status for {url}: {e}")


def update_database(
    urls: list[HttpUrl], now: datetime, website: Webiste
) -> DataBaseUpdate:
    n_deleted = mark_listings_as_deleted(urls, website=website)
    new_count, updated_count = upsert_listings(urls, now, website)
    status = DataBaseUpdate(
        website=website,
        n_new=new_count,
        n_deleted=n_deleted,
        n_updated=updated_count,
        date=now,
    )
    logger.success(f"Successfully updated {website}")
    updates_date.insert(to_json_serialiable(status.model_dump()))
    return status


def get_last_update(website: Webiste) -> Optional[DataBaseUpdate]:
    sofar = [
        DataBaseUpdate.model_validate(i)
        for i in updates_date.search(Query().website == website)
    ]
    if not sofar:
        return
    return max(sofar, key=lambda x: x.date)
