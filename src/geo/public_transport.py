import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv

from src.locations import ETH_LOCATION
from src.logger import logger
from src.models import Journey, PublicTransportConnection

assert load_dotenv()


def summarize_connection(conn: Dict[str, Any]) -> PublicTransportConnection:
    def _pdur(s: str) -> int:
        d, hms = s.split("d")
        h, m, sec = hms.split(":")
        return (int(d) * 24 + int(h)) * 3600 + int(m) * 60 + int(sec)

    best = min(conn["connections"], key=lambda c: _pdur(c["duration"]))
    secs = best["sections"]
    journeys: list[Journey] = []
    prev_ts = best["from"]["departureTimestamp"]

    for sec in secs:
        dep = sec["departure"]
        arr = sec["arrival"]
        d_ts, a_ts = dep["departureTimestamp"], arr["arrivalTimestamp"]
        wait = d_ts - (prev_ts or d_ts)
        if wait and wait > 60:
            journeys.append(
                Journey(
                    type="wait", length_min=wait // 60, latitude=None, longitude=None
                )
            )

        if sec.get("walk"):
            dur = sec["walk"]["duration"] or (a_ts - d_ts)
            lat = dep["location"]["coordinate"]["x"]
            lon = dep["location"]["coordinate"]["y"]
            journeys.append(
                Journey(type="walk", length_min=dur // 60, latitude=lat, longitude=lon)
            )
        elif sec.get("journey"):
            cat = sec["journey"]["category"]
            mins = (a_ts - d_ts) // 60
            lat = dep["location"]["coordinate"]["x"]
            lon = dep["location"]["coordinate"]["y"]
            journeys.append(
                Journey(type=cat, length_min=mins, latitude=lat, longitude=lon)
            )

        prev_ts = a_ts

    total_min = _pdur(best["duration"]) // 60
    return PublicTransportConnection(total_time_min=total_min, journeys=journeys)


def parse_duration(duration: str) -> int:
    m = re.match(r"(?:(\d+)d)?(\d+):(\d+):(\d+)", duration)
    d, h, mi, s = map(int, m.groups(default="0"))
    return d * 1440 + h * 60 + mi + s // 60


def fetch_public_transport_connection(
    from_lat: float,
    from_lon: float,
    to_lat: float = ETH_LOCATION.latitutude,
    to_lon: float = ETH_LOCATION.longitude,
) -> Optional[PublicTransportConnection]:
    today = datetime.today()
    at_time = (today - timedelta(days=today.weekday())).replace(
        hour=8, minute=0, second=0, microsecond=0
    )
    date_str = at_time.strftime("%Y-%m-%d")
    time_str = at_time.strftime("%H:%M")

    url = (
        "https://transport.opendata.ch/v1/connections"
        f"?from={from_lat},{from_lon}&to={to_lat},{to_lon}&date={date_str}&time={time_str}"
    )

    resp = requests.get(url)
    if not resp.ok:
        logger.error(
            f"Request failed with status code {resp.status_code}",
        )
        return None

    data = resp.json()
    if not data.get("connections"):
        logger.error("No connection found.")
        return None

    try:
        return summarize_connection(data)
    except Exception as e:
        logger.error("Error parsing connection: %s", e)
        return None
