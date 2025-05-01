import time
from concurrent.futures import ThreadPoolExecutor

from src.geo.bike import fetch_bike_connection
from src.geo.public_transport import fetch_public_transport_connection
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
    outputs: dict[str, BaseListing] = {}

    # split into minute-batches
    for minute_batch in chunked(inputs, max_requests_per_minute):
        # split each minute into second-batches
        minute_start = time.time()
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(
                executor.map(lambda args: fetch_commutes(*args), minute_batch)
            )
        for lst in results:
            outputs[str(lst.url)] = lst

        elapsed = time.time() - minute_start
        if elapsed < 60.0:
            time.sleep(60.0 - elapsed)
    # preserve original order
    return [outputs[str(scr.url)] for scr, _ in inputs]
