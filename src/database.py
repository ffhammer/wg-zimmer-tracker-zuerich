# database.py
import os
from datetime import datetime
from tinydb import TinyDB, Query
from tinydb.operations import set as tinyset  # Rename 'set' to avoid conflict
from typing import List, Set, Optional, Tuple, Literal
from models import ListingScraped, ListingStored, DataBaseUpdate
from logger import logger
from pathlib import Path
from pydantic import HttpUrl
from tqdm import tqdm
from fetch_listing_details import create_listing_stored


DB_FILE = os.path.join("db.json")
DATA_DIR = Path("listings")

db = TinyDB(DB_FILE, indent=4, ensure_ascii=False)
listings_table = db.table("listings")
updates_date = db.table("updates")
ListingQuery = Query()


def make_datetime_isonorm(dic: dict) -> dict:

    for key, val in dic.items():

        if isinstance(val, datetime):
            dic[key] = val.isoformat()
        if isinstance(val, HttpUrl):
            dic[key] = str(val)

    return dic


def get_listing_by_url(url: str) -> Optional[ListingStored]:
    """Holt ein spezifisches Listing anhand seiner URL."""
    result = listings_table.get(ListingQuery.url == url)
    if result:
        try:
            # Manually handle potential type errors during conversion
            return ListingStored(**result)
        except Exception as e:
            logger.error(
                f"Failed to parse listing from DB for URL {url}: {e}. Data: {result}"
            )
            return None
    return None


def upsert_listings(
    scraped_listings: List[ListingScraped], now: datetime
) -> Tuple[int, int]:
    """Fügt neue Listings hinzu oder aktualisiert bestehende.

    Returns:
        Tuple[int, int]: Anzahl neuer Listings, Anzahl aktualisierter Listings.
    """
    new_count = 0
    updated_count = 0

    for scraped in tqdm(scraped_listings, desc="Upserting"):
        if not scraped.url:
            logger.warning(f"Skipping listing due to missing URL: {scraped.adresse}")
            continue

        url_str = str(scraped.url)
        existing_doc = listings_table.get(ListingQuery.url == url_str)

        if existing_doc:
            updated_count += update(scraped, url_str, existing_doc, now)

        else:
            new_count += insert(now, scraped, url_str)

    return new_count, updated_count


def insert(now, scraped, url_str):
    try:
        stored_listing = create_listing_stored(scraped, now)
        insert_data = stored_listing.model_dump()
        listings_table.insert(make_datetime_isonorm(insert_data))
        return True
    except Exception as e:
        logger.error(f"Error inserting new listing {url_str}: {e}.")

    return False


def update(scraped, url_str, existing_doc, now):
    try:
        existing_listing = ListingStored(**existing_doc)
        existing_listing.update_from_scraped(scraped, now)
        return True
    except Exception as e:
        logger.error(f"Error updating listing {url_str}: {e}. Data: {existing_doc}")
    return False


def mark_listings_as_deleted(active_urls_in_fetch: Set[str]) -> int:
    """Markiert Listings in der DB als 'deleted', wenn sie nicht im letzten Fetch waren."""
    deleted_count = 0
    active_listings_in_db = listings_table.search(ListingQuery.status == "active")

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


def get_all_listings_stored(include_deleted=False) -> List[ListingStored]:
    """Holt alle Listings aus der DB."""
    if include_deleted:
        results = listings_table.all()
    else:
        results = listings_table.search(ListingQuery.status == "active")

    return [ListingStored.model_validate(doc) for doc in results]


def update_listing_user_status(
    url: str, field: Literal["gesehen", "gemerkt"], value: bool
) -> bool:
    """Aktualisiert den 'gesehen' oder 'gemerkt' Status eines Listings."""
    logger.debug(f"Updating DB: set {field}={value} for url={url}")
    try:
        listings_table.update({field: value}, ListingQuery.url == url)
    except Exception as e:
        logger.error(f"Error updating user status for {url}: {e}")


def update_database(path: Path, dt: datetime) -> DataBaseUpdate:
    assert path.exists(), f"file should exist: {path}"
    logger.info(f"Starting to update {path}")
    listings_unique = [
        ListingScraped.model_validate_json(i)
        for i in set(path.read_text().splitlines())
    ]
    n_deleted = mark_listings_as_deleted({str(i.url) for i in listings_unique})
    new_count, updated_count = upsert_listings(listings_unique, now=dt)
    status = DataBaseUpdate(
        n_new=new_count, n_deleted=n_deleted, n_updated=updated_count, date=dt
    )
    logger.info(f"Sucessfully processed {path} with {status}")
    updates_date.insert(make_datetime_isonorm(status.model_dump()))
    return status


def get_last_update() -> Optional[DataBaseUpdate]:
    sofar = [DataBaseUpdate.model_validate(i) for i in updates_date.all()]

    if not sofar:
        return

    return max(sofar, key=lambda x: x.date)


def check_for_new_data_and_update() -> list[DataBaseUpdate]:

    dates = [
        datetime.fromisoformat(i.replace(".jsonl", "")) for i in os.listdir(DATA_DIR)
    ]

    last_update = get_last_update()

    new = [i for i in dates if (not last_update) or last_update.date < i]

    vals = []
    for path in new:
        file = DATA_DIR / f"{path.isoformat()}.jsonl"
        vals.append(update_database(file, dt=path))
    return vals


if __name__ == "__main__":
    print(check_for_new_data_and_update())
    print(len(get_all_listings_stored()))
