import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pydantic import HttpUrl
from tqdm import tqdm

from src.geo.fetch_location import fetch_cordinates
from src.logger import logger
from src.models import (
    WGZimmerCHListing,
)

assert load_dotenv()


def fetch_listing(url: HttpUrl, now: WGZimmerCHListing) -> WGZimmerCHListing:
    """
    Fetch a WGZimmer.ch listing page and return a populated WGZimmerCHListing model.
    Extracts region, address, availability dates, rent, description, images and coordinates.
    May raise on HTTP or parsing errors.
    """
    # after soup = BeautifulSoup(...)
    response = requests.get(url)

    if not response.ok:
        raise requests.HTTPError(f"Failed fetching {url} - {response.status_code}")

    soup = BeautifulSoup(response.content, "html.parser")
    meta_date = soup.find("meta", {"name": "DC.Date"})["content"]
    aufgegeben = datetime.strptime(meta_date, "%Y-%m-%d")
    date_div = soup.select_one("div.col-wrap.date-cost")
    for p in date_div.find_all("p"):
        key = p.find("strong").get_text(strip=True)
        val = p.get_text(separator=" ", strip=True).replace(key, "").strip()
        if key == "Ab dem":
            datum_ab = datetime.strptime(val, "%d.%m.%Y")
        elif key == "Bis":
            frei_bis = val if val != "Unbefristet" else None
        elif key.startswith("Miete"):
            miete = float(re.search(r"(\d+)", val).group(1))

    address_div = soup.select_one("div.adress-region")

    def extract_nested_value(name: str) -> str | None:
        try:
            val = address_div.find("strong", string=name)
            return val.next_sibling.strip() if val and val.next_sibling else None
        except Exception as e:
            logger.error(f"extracting {name} failed with {e}")

    region = extract_nested_value("Region")
    straße_und_hausnummer = extract_nested_value("Adresse")
    plz_und_stadt = extract_nested_value("Ort")

    def extract_simple_value(query: str) -> str | None:
        try:
            res = soup.select_one(query)

            return res.get_text(separator=" ", strip=True) if res else None
        except Exception as e:
            logger.error(f"extracting {query} failed with {e}")

    beschreibung = extract_simple_value("div.mate-content > p")
    wir_suchen = extract_simple_value("div.room-content > p")
    wir_sind = extract_simple_value("div.person-content > p")

    base_url = "https://www.wgzimmer.ch"
    img_urls = list(
        {
            tag["content"]
            for tag in soup.find_all("meta", {"property": "og:image"})
            if tag.get("content")
        }.union(
            {
                base_url + img["src"]
                for img in soup.find_all("img")
                if img.get("src") and img["src"].startswith("/docroot/img.wgzimmer.ch")
            }
        ).difference(("https://www.wgzimmer.ch/docroot/img.wgzimmer.ch/loading.gif",))
    )

    match = re.search(
        rb"ol\.proj\.fromLonLat\(\[\s*([+-]?\d+\.\d+)\s*,\s*([+-]?\d+\.\d+)\s*\]\)",
        response.content,
    )
    if match:
        longitude, latitude = (
            float(match.group(1)),
            float(match.group(2)),
        )
    else:
        logger.info(
            "could not fetch longitude and langitude from the map. using the api"
        )
        latitude, longitude = fetch_cordinates(
            straße_und_hausnummer=straße_und_hausnummer,
            plz_und_stadt=plz_und_stadt,
            region=region,
        )

    return WGZimmerCHListing(
        aufgegeben_datum=aufgegeben,
        miete=miete,
        datum_ab_frei=datum_ab,
        datum_frei_bis=frei_bis,
        region=region,
        beschreibung=beschreibung,
        wir_suchen=wir_suchen,
        wir_sind=wir_sind,
        img_urls=img_urls,
        longitude=longitude,
        latitude=latitude,
        plz_und_stadt=plz_und_stadt,
        straße_und_hausnummer=straße_und_hausnummer,
        first_seen=now,
        url=url,
    )


def fetch_listings(
    urls: list[HttpUrl],
    now: datetime,
) -> list[WGZimmerCHListing]:
    try:
        return [
            l
            for u in tqdm(urls, desc="Fetching Individual Listings")
            if (l := fetch_listing(u, now=now))
        ]

    except Exception as e:
        logger.error(f"Failed fetching listings from table: {e}")
        return []
