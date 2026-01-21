import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from sqlmodel import Session

from src.database import enginge, get_all_listings_stored
from src.geo.commutes import batch_fetch_commutes
from src.logger import logger
from src.models import ListingSQL


def update_recent_commutes(limit: int = 30):
    logger.info(f"Fetching all listings to find the {limit} most recent...")
    all_listings = get_all_listings_stored(include_deleted=True)

    # Sort by listing date (aufgegeben_datum), fallback to first_seen if None
    all_listings.sort(key=lambda x: x.aufgegeben_datum or x.first_seen, reverse=True)

    targets = all_listings[:limit]
    logger.info(f"Refetching commutes for {len(targets)} listings...")

    # This will fetch both ETH and Stark connections as per recent model changes
    for i in targets:
        i.bike_stark = None
        i.public_transport_stark = None
        i.public_transport = None
    updated_listings = batch_fetch_commutes(targets, max_requests_per_minute=10)

    logger.info("Saving updates to database...")
    with Session(enginge) as session:
        for listing in updated_listings:
            # ListingSQL.from_pydantic uses the URL as PK, so this performs an upsert
            sql_listing = ListingSQL.from_pydantic(listing)
            session.merge(sql_listing)
        session.commit()

    logger.success(
        f"Successfully updated commutes for {len(updated_listings)} listings."
    )


if __name__ == "__main__":
    update_recent_commutes(30)
