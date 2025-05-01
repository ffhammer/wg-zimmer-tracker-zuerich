import re
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup
from pydantic import HttpUrl
from tqdm import tqdm

from src.logger import logger
from src.models import WokoListing


def fetch_listing(url: str, now: datetime) -> Optional[WokoListing]:
    try:
        r = requests.get(url)
        if not r.ok:
            logger.error(f"{r.status_code} for {url}")
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        tables = soup.select(".inserat-details table")
        rows = tables[0].find_all("tr")
        # availability, address, rent
        date_row = rows[0].find_all("td")[1].text

        ab = re.search(r"ab (\d{2}\.\d{2}\.\d{4})", date_row).group(1)

        bis = None
        if match := re.search(r"bis (\d{2}\.\d{2}\.\d{4})", date_row):
            bis = datetime.strptime(match.group(1), "%d.%m.%Y")

        addr = rows[1].find_all("td")[1].text.strip()
        m = float(re.search(r"(\d+)", rows[2].find_all("td")[1].text).group(1))
        street, city = [s.strip() for s in addr.split(",", 1)]
        # contact email
        contact = tables[1]
        mail = contact.find("a", href=re.compile(r"mailto:"))["href"].split(":", 1)[1]
        # sonstiges description
        sonstiges = tables[2].find("td", string="Sonstiges")
        desc = (
            sonstiges.find_next_sibling("td").get_text(" ").strip() if sonstiges else ""
        )
        # images
        imgs = [
            "https://www.woko.ch" + a["href"]
            for a in soup.select(".inserat-details a[target='_image']")
        ]
        # lat/lng
        js = next(s.text for s in soup.find_all("script") if "var marker" in s.text)
        lat = float(re.search(r'"lat":\s*"([\d.]+)"', js).group(1))
        lng = float(re.search(r'"lng":\s*"([\d.]+)"', js).group(1))
        return WokoListing(
            url=url,
            datum_ab_frei=datetime.strptime(ab, "%d.%m.%Y"),
            datum_frei_bis=bis,
            straße_und_hausnummer=street,
            plz_und_stadt=city,
            miete=m,
            contact_mail=mail,
            beschreibung=desc,
            img_urls=imgs,
            latitude=lat,
            longitude=lng,
            first_seen=now,
        )
    except Exception as e:
        logger.exception(f"parse failed for {url}: {e}")
        return None


def fetch_table(
    page_url: str = "https://www.woko.ch/de/zimmer-in-zuerich",
) -> list[HttpUrl]:
    resp = requests.get(page_url)
    if not resp.ok:
        logger.error(f"Failed to fetch listing table: {resp.status_code}")
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    links = soup.select(".inserat a[href*='/de/zimmer-in-zuerich-details/']")
    return [HttpUrl("https://www.woko.ch" + a["href"]) for a in links]


def fetch_listings(
    urls: list[HttpUrl],
    now: datetime,
) -> list[WokoListing]:
    try:
        return [
            l
            for u in tqdm(urls, desc="Fetching Individual Listings")
            if (l := fetch_listing(u, now=now))
        ]

    except Exception as e:
        logger.error(f"Failed fetching listings from table: {e}")
        return []
