import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import polyline
import requests
from dotenv import load_dotenv

from src.eth_location import ETH_LOCATION
from src.logger import logger
from src.models import BikeConnection, Journey, PublicTransportConnection

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


def fetch_journey(
    from_lat: float, from_lon: float, at_time: datetime = datetime(2025, 4, 30, 8, 0)
) -> Optional[PublicTransportConnection]:
    date_str = at_time.strftime("%Y-%m-%d")
    time_str = at_time.strftime("%H:%M")

    url = (
        "https://transport.opendata.ch/v1/connections"
        f"?from={from_lat},{from_lon}&to={ETH_LOCATION.latitutude},{ETH_LOCATION.longitude}&date={date_str}&time={time_str}"
    )

    resp = requests.get(url)
    if not resp.ok:
        logger.error("Request failed with status code %s", resp.status_code)
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


def fetch_bike_connection(
    from_lat: float,
    from_lon: float,
) -> Optional[BikeConnection]:
    url = "https://api.openrouteservice.org/v2/directions/cycling-regular"
    headers = {
        "Authorization": os.environ["OPENROUTESERVICE_API_KEY"],
        "Content-Type": "application/json",
    }
    body = {
        "coordinates": [
            [from_lon, from_lat],
            [ETH_LOCATION.longitude, ETH_LOCATION.latitutude],
        ]
    }
    try:
        resp = requests.post(url, json=body, headers=headers, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        routes = data.get("routes", [])
        best = min(routes, key=lambda r: r["summary"]["duration"])
        dist_km = best["summary"]["distance"] / 1000
        time_min = best["summary"]["duration"] / 60

        coords: List[tuple[float, float]] = polyline.decode(best["geometry"])

        # extract each step’s slice of coords
        waypoints: List = []
        for seg in best["segments"]:
            for step in seg["steps"]:
                start, end = step["way_points"]

                for lat, lon in coords[start : end + 1 : 2]:
                    waypoints.append({"latitude": lat, "longitude": lon})
        return BikeConnection(
            duration_min=time_min, dist_km=dist_km, waypoints=waypoints
        )
    except requests.RequestException as e:
        logger.error("Bike request failed: %s", e)
    except (KeyError, IndexError) as e:
        logger.error("Error parsing bike response: %s", e)
    return None


if __name__ == "__main__":
    res = fetch_journey(47.396201, 8.52830)
    print("pub", res.__repr__() if res else "None")

    res = fetch_bike_connection(47.396201, 8.52830)
    print("bike", res.__repr__() if res else "None")
