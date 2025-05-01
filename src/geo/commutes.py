import time
from concurrent.futures import ThreadPoolExecutor

from tqdm import tqdm

from src.geo.bike import fetch_bike_connection
from src.geo.public_transport import fetch_public_transport_connection
from src.logger import logger
from src.models import BaseListing


def chunked(lst: list, n: int) -> list[list]:
    return [lst[i : i + n] for i in range(0, len(lst), n)]


def fetch_commutes(listing: BaseListing) -> BaseListing:
    assert listing.latitude and listing.longitude

    if not listing.bike:
        listing.bike = fetch_bike_connection(
            from_lat=listing.latitude, from_lon=listing.longitude
        )
    if not listing.public_transport:
        listing.public_transport = fetch_public_transport_connection(
            from_lat=listing.latitude, from_lon=listing.longitude
        )
    return listing


def batch_fetch_commutes(
    inputs: list[BaseListing],
    max_requests_per_minute: int = 40,
) -> list[BaseListing]:
    logger.debug(f"Starting commutes fetching for {len(inputs)}")
    outputs: dict[str, BaseListing] = {}

    chunks = chunked(inputs, max_requests_per_minute)
    # split into minute-batches
    for i, minute_batch in enumerate(chunks):
        # split each minute into second-batches
        minute_start = time.time()
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(fetch_commutes, tqdm(minute_batch)))
        for lst in results:
            outputs[str(lst.url)] = lst

        elapsed = time.time() - minute_start
        if elapsed < 60.0 and i + 1 < len(chunks):
            t = 60.0 - elapsed
            logger.info(f"sleeping for {t} to not overstress geo apis rate limits")
            time.sleep(t)
    # preserve original order
    return [outputs[str(scr.url)] for scr in inputs]
