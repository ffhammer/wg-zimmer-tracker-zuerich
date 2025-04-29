# database.py
import os
from tinydb import TinyDB, Query
from tinydb.operations import set as tinyset  # Rename 'set' to avoid conflict
from typing import List, Set, Optional, Tuple, Literal
from models import ListingScraped, ListingStored
from datetime import datetime
import logging


logger = logging.getLogger(__name__)

DB_DIR = "listings"
DB_FILE = os.path.join(DB_DIR, "db.json")
os.makedirs(DB_DIR, exist_ok=True)

db = TinyDB(DB_FILE, indent=4, ensure_ascii=False)
listings_table = db.table("listings")
ListingQuery = Query()


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


def upsert_listings(scraped_listings: List[ListingScraped]) -> Tuple[int, int]:
    """Fügt neue Listings hinzu oder aktualisiert bestehende.

    Returns:
        Tuple[int, int]: Anzahl neuer Listings, Anzahl aktualisierter Listings.
    """
    new_count = 0
    updated_count = 0
    now = datetime.now()

    for scraped in scraped_listings:
        if not scraped.url:
            logger.warning(f"Skipping listing due to missing URL: {scraped.adresse}")
            continue

        url_str = str(scraped.url)
        existing_doc = listings_table.get(ListingQuery.url == url_str)

        if existing_doc:
            try:
                existing_listing = ListingStored(**existing_doc)  # Load existing data
                existing_listing.update_from_scraped(
                    scraped
                )  # Update fields and set status='active'
                update_data = {
                    "miete": existing_listing.miete,
                    "adresse": existing_listing.adresse,
                    "img_url": (
                        str(existing_listing.img_url)
                        if existing_listing.img_url
                        else None
                    ),
                    "aufgegeben_datum": (
                        existing_listing.aufgegeben_datum.isoformat()
                        if existing_listing.aufgegeben_datum
                        else None
                    ),
                    "datum_ab_frei": (
                        existing_listing.datum_ab_frei.isoformat()
                        if existing_listing.datum_ab_frei
                        else None
                    ),
                    "last_seen": existing_listing.last_seen.isoformat(),
                    "status": "active",
                }
                listings_table.update(update_data, ListingQuery.url == url_str)
                updated_count += 1
            except Exception as e:
                logger.error(
                    f"Error updating listing {url_str}: {e}. Data: {existing_doc}"
                )

        else:
            try:
                stored_listing = ListingStored(
                    **scraped.model_dump(exclude_none=True),  # Use scraped data
                    url=scraped.url,  # Ensure URL is set
                    first_seen=now,
                    last_seen=now,
                    status="active",
                    gesehen=False,  # Default values
                    gemerkt=False,
                )
                # Convert datetime/HttpUrl back to string for JSON storage
                insert_data = stored_listing.model_dump(mode="json")
                listings_table.insert(insert_data)
                new_count += 1
            except Exception as e:
                logger.error(
                    f"Error inserting new listing {url_str}: {e}. Scraped data: {scraped}"
                )

    return new_count, updated_count


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
                logger.info(f"Marked listing as deleted: {listing_doc['url']}")
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

    listings = []
    for doc in results:
        try:
            listings.append(ListingStored(**doc))
        except Exception as e:
            logger.error(f"Failed to parse listing from DB: {e}. Data: {doc}")
    return listings


def update_listing_user_status(
    url: str, field: Literal["gesehen", "gemerkt"], value: bool
) -> bool:
    """Aktualisiert den 'gesehen' oder 'gemerkt' Status eines Listings."""
    logger.debug(f"Updating DB: set {field}={value} for url={url}")
    try:
        updated_count = listings_table.update({field: value}, ListingQuery.url == url)
        return len(updated_count) > 0  # Returns list of updated doc_ids
    except Exception as e:
        logger.error(f"Error updating user status for {url}: {e}")
        return False
