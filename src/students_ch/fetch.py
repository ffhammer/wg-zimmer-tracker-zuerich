import re
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup
from pydantic import HttpUrl
from tqdm import tqdm

from src.geo.fetch_location import fetch_cordinates
from src.logger import logger
from src.models import StudentsCHListing


def fetch_listing(url: str, now: datetime) -> Optional[StudentsCHListing]:
    response = requests.get(url)
    if not response.ok:
        logger.error(f"Received {response.status_code} for {url}")
        return
    try:
        return parse_html(response.content, url, now)
    except Exception as e:
        logger.error(f"failed parsing '{url}' with {e}")


def parse_html(html: str, url: str, now: datetime) -> StudentsCHListing:
    soup = BeautifulSoup(html, "html.parser")
    # posting date

    date_post = soup.find(string=re.compile(r"\d{2}\.\d{2}\.\d{4}"))
    aufgegeben_datum = datetime.strptime(date_post.strip(), "%d.%m.%Y")
    # address
    addr = soup.find("h3").text.strip()
    adresse = addr
    street, city = [s.strip() for s in addr.split(",", 1)]
    straße_und_hausnummer = street
    plz_und_stadt = city
    # description
    box = soup.find("div", class_="box_large") or soup.find(
        "div", class_="floatbox box_large"
    )
    desc = box.get_text(separator="\n").split("\n", 1)[1].strip()
    beschreibung = desc
    # details & rent & size
    det = soup.find("div", string="Details").find_next_sibling("div").get_text()
    miete = float(re.search(r"(\d+)", det).group(1))
    größe_in_m2 = float(re.search(r"(\d+)", det.split("Grösse:")[1]).group(1))
    # availability
    avail = soup.find("div", string="Verfügbarkeit").find_next_sibling("div").get_text()
    ab, bis = re.findall(r"Frei ab: ([\d\.]+)|Frei bis: (\w+)", avail)
    datum_ab_frei = datetime.strptime(ab[0], "%d.%m.%Y")
    datum_frei_bis = bis[1] if bis[1] else None
    # images
    imgs = soup.select(".box_small a[data-lightbox]")
    img_urls = [a["href"] for a in imgs]

    lat, lon = fetch_cordinates(
        straße_und_hausnummer=straße_und_hausnummer,
        plz_und_stadt=plz_und_stadt,
        region="Zürich (Stadt)",
    )

    return StudentsCHListing(
        url=url,
        aufgegeben_datum=aufgegeben_datum,
        adresse=adresse,
        straße_und_hausnummer=straße_und_hausnummer,
        plz_und_stadt=plz_und_stadt,
        beschreibung=beschreibung,
        miete=miete,
        größe_in_m2=größe_in_m2,
        datum_ab_frei=datum_ab_frei,
        datum_frei_bis=datum_frei_bis,
        img_urls=img_urls,
        first_seen=now,
        latitude=lat,
        longitude=lon,
    )


def fetch_table(
    page_url: str = "https://www.students.ch/wohnen/list/140?type=wg&price-range-min=0&price-range-max=1000&room-range-min=1&room-range-max=10&square-meter-range-min=0&square-meter-range-max=500",
) -> list[HttpUrl]:
    resp = requests.get(page_url)
    if not resp.ok:
        logger.error(f"Failed to fetch listing table: {resp.status_code}")
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    links = soup.select('table.list_table a[href*="/wohnen/details/"]')
    return [HttpUrl("https://www.students.ch" + a["href"]) for a in links]


def fetch_listings(
    urls: list[HttpUrl],
    now: datetime,
) -> list[StudentsCHListing]:
    try:
        return [
            l
            for u in tqdm(urls, desc="Fetching Individual Listings")
            if (l := fetch_listing(u, now=now))
        ]

    except Exception as e:
        logger.error(f"Failed fetching listings from table: {e}")
        return []
