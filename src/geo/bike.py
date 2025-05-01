import os
from typing import List, Optional

import polyline
import requests
from dotenv import load_dotenv

from src.eth_location import ETH_LOCATION
from src.logger import logger
from src.models import BikeConnection

assert load_dotenv()


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
        logger.error(f"Bike request failed: {e}")
    except (KeyError, IndexError) as e:
        logger.error(f"Error parsing bike response: {e}")
    return None
