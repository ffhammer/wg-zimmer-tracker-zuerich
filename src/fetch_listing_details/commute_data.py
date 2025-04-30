import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import polyline
import requests
from dotenv import load_dotenv

from src.logger import logger
from src.models import BikeConnection, Journey, PublicTransportConnection

assert load_dotenv()


def summarize_connection(conn: Dict[str, Any]) -> PublicTransportConnection:
    journeys: List[Journey] = []
    last_ts = conn["from"].get("departureTimestamp")

    for sec in conn["sections"]:
        dep = sec["departure"]
        arr = sec["arrival"]
        dep_ts, arr_ts = dep.get("departureTimestamp"), arr.get("arrivalTimestamp")
        coord = dep["location"]["coordinate"]
        lat, lon = coord["x"], coord["y"]

        if sec.get("journey"):
            if last_ts and dep_ts and dep_ts > last_ts:
                journeys.append(
                    Journey(
                        type="wait",
                        length_min=(dep_ts - last_ts) // 60,
                        latitude=lat,
                        longitude=lon,
                    )
                )
            journeys.append(
                Journey(
                    type=sec["journey"]["category"],
                    length_min=(arr_ts - dep_ts) // 60,
                    latitude=lat,
                    longitude=lon,
                )
            )
            last_ts = arr_ts
        else:
            if dep_ts and arr_ts and arr_ts > dep_ts:
                journeys.append(
                    Journey(
                        type="walk",
                        length_min=(arr_ts - dep_ts) // 60,
                        latitude=lat,
                        longitude=lon,
                    )
                )
            last_ts = arr_ts or last_ts

    total_time_min = (
        conn["to"]["arrivalTimestamp"] - conn["from"]["departureTimestamp"]
    ) // 60
    return PublicTransportConnection(total_time_min=total_time_min, journeys=journeys)


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
        f"?from={from_lat},{from_lon}&to=47.3763,8.5476&date={date_str}&time={time_str}"
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
        best = min(data["connections"], key=lambda c: parse_duration(c["duration"]))
        return summarize_connection(best)
    except Exception as e:
        logger.error("Error parsing connection: %s", e)
        return None


def fetch_bike_connection(
    from_lat: float,
    from_lon: float,
    to_lat: float = 47.3763,
    to_lon: float = 8.5476,
) -> Optional[BikeConnection]:
    url = "https://api.openrouteservice.org/v2/directions/cycling-regular"
    headers = {
        "Authorization": os.environ["OPENROUTESERVICE_API_KEY"],
        "Content-Type": "application/json",
    }
    body = {"coordinates": [[from_lon, from_lat], [to_lon, to_lat]]}
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
