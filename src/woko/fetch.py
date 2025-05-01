import re
from datetime import datetime
from typing import List, Optional

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from src.logger import logger
from src.models import WokoListing


def fetch_listing(url: str) -> Optional[WokoListing]:
    try:
        r = requests.get(url)
        if not r.ok:
            logger.error(f"{r.status_code} for {url}")
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        tables = soup.select(".inserat-details table")
        rows = tables[0].find_all("tr")
        # availability, address, rent
        ab = re.search(
            r"ab (\d{2}\.\d{2}\.\d{4})", rows[0].find_all("td")[1].text
        ).group(1)
        addr = rows[1].find_all("td")[1].text.strip()
        m = float(re.search(r"(\d+)", rows[2].find_all("td")[1].text).group(1))
        street, city = [s.strip() for s in addr.split(",", 1)]
        # contact email
        contact = tables[1]
        mail = contact.find("a", href=re.compile(r"mailto:"))["href"].split(":", 1)[1]
        # sonstiges description
        desc_row = tables[2].find("td", string="Sonstiges").find_next_sibling("td")
        desc = desc_row.get_text(" ").strip()
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
            adresse=addr,
            straße_und_hausnummer=street,
            plz_und_stadt=city,
            miete=m,
            contact_mail=mail,
            beschreibung=desc,
            img_urls=imgs,
            latitude=lat,
            longitude=lng,
        )
    except Exception as e:
        logger.error(f"parse failed for {url}: {e}")
        return None


def fetch_all_listings(
    page_url: str = "https://www.woko.ch/de/nachmieter-gesucht",
) -> List[WokoListing]:
    try:
        now = datetime.now()
        r = requests.get(page_url)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        links = soup.select(".inserat a[href*='/de/zimmer-in-zuerich-details/']")
        urls = ["https://www.woko.ch" + a["href"] for a in links]
        listings = [
            listing
            for u in tqdm(urls, desc="Fetch Woko listings")
            if (listing := fetch_listing(u))
        ]

        for l in listings:
            l.first_seen = now
        return listings
    except Exception as e:
        logger.error(f"fetch listings failed: {e}")
        return []
