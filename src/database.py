# database.py
import os
from datetime import datetime
from typing import List, Literal, Optional, Tuple

from pydantic import HttpUrl
from sqlmodel import Session, create_engine, select
from tinydb import Query, TinyDB

from src import students_ch, wg_zimmer_ch, woko
from src.geo.commutes import batch_fetch_commutes
from src.logger import logger
from src.models import (
    WEBSITE_TO_MODEL,
    BaseListing,
    DataBaseUpdate,
    ExampleDraft,
    ListingSQL,
    StudentsCHListing,
    Webiste,
    WGZimmerCHListing,
    WokoListing,
)

DB_FILE = os.path.join("db.json")
MAX_GEO_REQEUSTS_PER_MINUTE = 33

enginge = create_engine("sqlite:///listings.db")
db = TinyDB(DB_FILE, indent=4, ensure_ascii=False)
updates_table = db.table("updates")
drafts_table = db.table("drafts")
query = Query()


def to_json_serialiable(dic: dict) -> dict:
    for key, val in dic.items():
        if isinstance(val, datetime):
            dic[key] = val.isoformat()
        if isinstance(val, HttpUrl):
            dic[key] = str(val)

    return dic


def get_listing_by_url(url: str) -> Optional[BaseListing]:
    """Holt ein spezifisches Listing anhand seiner URL."""

    with Session(enginge) as session:
        val = session.get(ListingSQL, url)

    return val.to_pydantic() if val else None


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
        existing_doc = get_listing_by_url(str(url))
        if existing_doc:
            model = load_correct(existing_doc)
            model.update(now)
            existing_doc.update(model.dump_json_serializable())
            updated_count += 1
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

        with Session(enginge) as session:
            session.add_all(
                [ListingSQL.from_pydantic(listings) for listings in listings]
            )
            session.commit()
        return len(listings)
    except Exception as e:
        logger.exception(f"Error inserting new listing failed: {e}.")

    return False


def load_correct(json) -> WGZimmerCHListing | StudentsCHListing | WokoListing:
    return WEBSITE_TO_MODEL[json["website"]].model_validate(json)


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
    with Session(enginge) as session:
        statement = select(ListingSQL).where(
            ListingSQL.status == "active", ListingSQL.website == website
        )
        listings = session.exec(statement).all()
        for listing in listings:
            if listing.url not in active_urls_in_fetch:
                try:
                    listing.status = "deleted"
                    session.add(listing)
                    deleted_count += 1
                    logger.debug(f"Marked listing as deleted: {listing.url}")
                except Exception as e:
                    logger.error(f"Error marking listing as deleted {listing.url}: {e}")
        session.commit()
    return deleted_count


def get_all_listings_stored(include_deleted=False) -> List[BaseListing]:
    """Holt alle Listings aus der DB."""
    with Session(enginge) as session:
        if include_deleted:
            statement = select(ListingSQL)
        else:
            statement = select(ListingSQL).where(ListingSQL.status == "active")
        listings = session.exec(statement).all()
        return [listings.to_pydantic() for listings in listings]


def update_listing_user_status(
    url: str, field: Literal["gesehen", "gemerkt"], value: bool
) -> bool:
    """Aktualisiert den 'gesehen' oder 'gemerkt' Status eines Listings."""
    logger.debug(f"Updating DB: set {field}={value} for url={url}")
    with Session(enginge) as session:
        listing = session.get(ListingSQL, url)
        if listing:
            setattr(listing, field, value)
            session.commit()
            return True
        else:
            logger.error(f"Listing not found for url={url}")
            return False


def update_database(
    urls: list[HttpUrl], now: datetime, website: Webiste
) -> DataBaseUpdate:
    if website != Webiste.wg_zimmer_ch:
        n_deleted = mark_listings_as_deleted(urls, website=website)
    else:
        n_deleted = 0
    new_count, updated_count = upsert_listings(urls, now, website)
    status = DataBaseUpdate(
        website=website,
        n_new=new_count,
        n_deleted=n_deleted,
        n_updated=updated_count,
        date=now,
    )
    logger.success(f"Successfully updated {website}")
    updates_table.insert(to_json_serialiable(status.model_dump()))
    return status


def get_last_update(website: Webiste) -> Optional[DataBaseUpdate]:
    sofar = [
        DataBaseUpdate.model_validate(i)
        for i in updates_table.search(Query().website == website)
    ]
    if not sofar:
        return
    return max(sofar, key=lambda x: x.date)


def save_draft(draft: ExampleDraft) -> None:
    logger.debug(f"saving draft for {draft.listing_url}")
    drafts_table.remove(query.listing_url == draft.listing_url)
    drafts_table.insert(to_json_serialiable(draft.model_dump()))


def load_saved_draft_listing_pairs() -> list[tuple[BaseListing, ExampleDraft]]:
    output = []
    for draft in drafts_table.all():
        draft = ExampleDraft.model_validate(draft)

        listing = get_listing_by_url(str(draft.listing_url))
        if listing:
            output.append((listing, draft))
        else:
            logger.error(f"Could not find listing {draft.listing_url}")
    return output
