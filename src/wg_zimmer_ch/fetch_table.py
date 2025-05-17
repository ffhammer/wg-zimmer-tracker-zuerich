import json
import logging
import os
import random
import re
import sys
import time
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import pytz
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from playwright.sync_api import Playwright, sync_playwright
from tqdm import tqdm

TIME_ZONE = pytz.timezone(os.environ["TIME_ZONE"])


path_to_extension = "uBlock0.chromium"
user_data_dir = "chromium-user-data-dir"


load_dotenv()

# LOG_FILE_PATH = "/app/app.log"  # Log file inside the container
# SAVE_DIR = "wg-zimmer-listings"

LOG_FILE_PATH = "app.log"  # Log file inside the container
SAVE_DIR = "wg-zimmer-listings"

LOG_LEVEL = logging.INFO

# --- Configure Logging to File ---
log_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# File Handler
file_handler = logging.FileHandler(LOG_FILE_PATH, mode="a")  # 'a' for append
file_handler.setFormatter(log_formatter)

# Get root logger and add the file handler
root_logger = logging.getLogger()
root_logger.setLevel(LOG_LEVEL)
# Remove existing handlers if basicConfig was somehow called before or by libraries implicitly
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)
# Add our file handler
root_logger.addHandler(file_handler)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)
root_logger.addHandler(console_handler)

sys.stdout.reconfigure(line_buffering=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)


def parse_wgzimmer_search_results(
    html_content: str, base_url: str = "https://www.wgzimmer.ch"
) -> Tuple[Optional[int], Optional[int], List[str]]:
    """
    Parses the HTML content of a wgzimmer.ch search results page.

    Args:
        html_content: The HTML content as a string.
        base_url: The base URL for constructing absolute URLs.

    Returns:
        A tuple containing:
        - current_page (Optional[int]): The current page number.
        - total_pages (Optional[int]): The total number of pages.
        - listings (List[Listing]): A list of parsed Listing objects.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    current_page: Optional[int] = None
    total_pages: Optional[int] = None
    listings: List[str] = []

    # 1. Parse Pagination
    # Find the pagination element (there might be two identical ones, top/bottom)
    pagination_span = soup.select_one("div.skip span.counter")
    if pagination_span:
        counter_text = pagination_span.get_text(strip=True)
        # Expected format: "Seite 1/4"
        match = re.search(r"Seite\s*(\d+)/(\d+)", counter_text)
        if match:
            try:
                current_page = int(match.group(1))
                total_pages = int(match.group(2))
            except (ValueError, IndexError):
                print(
                    f"Warning: Could not parse pagination numbers from: {counter_text}"
                )
        else:
            print(f"Warning: Pagination text format unexpected: {counter_text}")

    # 2. Parse Listings
    list_container = soup.select_one("ul.list#search-result-list")
    if list_container:
        # Select only direct children 'li' that are actual entries (not ad slots)
        list_items = list_container.select(
            "li.search-result-entry:not(.search-result-entry-slot)"
        )

        for item in list_items:
            try:
                # --- Extract URL ---
                link_tag = item.select_one("a")
                relative_url = link_tag["href"] if link_tag else None
                listings.append(
                    urljoin(base_url, relative_url) if relative_url else None
                )

            except Exception as e:
                # Catch any unexpected error during parsing a single list item
                print(f"Warning: Failed to parse a list item. Error: {e}")
                # Optionally log the problematic item HTML: print(item.prettify())
                continue  # Skip to the next item

    return current_page, total_pages, listings


def main(playwright: Playwright) -> List[str]:
    listings: List[str] = []

    context = playwright.chromium.launch_persistent_context(
        user_data_dir,
        headless=False,
        args=[
            f"--disable-extensions-except={path_to_extension}",
            f"--load-extension={path_to_extension}",
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-gpu",
            "--window-size=1920,1080",
            "--disable-features=IsolateOrigins,site-per-process",
        ],
    )
    page = context.pages[0]
    page.wait_for_timeout(1000)

    page.goto(
        "https://www.wgzimmer.ch/de/wgzimmer/search/mate/ch/zurich-stadt.html",
    )
    time.sleep(random.uniform(3, 5))
    # click "Ab dem" ascending
    page.locator('a.sort[href*="orderDir=asc"]:has-text("Ab dem")').click()
    # optional wait
    time.sleep(random.uniform(1, 2))
    # click "Ab dem" descending
    page.locator('a.sort[href*="orderDir=desc"]:has-text("Ab dem")').click()

    # Initial fetch to determine total pages
    html = page.content()
    current, total, links = parse_wgzimmer_search_results(html)
    listings.extend(links)

    if total is None:
        logging.warning(
            "Could not determine total number of pages. Progress bar will not be shown."
        )
        total = 1

    progress = tqdm(
        total=total, initial=current if current else 1, desc="Pages", unit="page"
    )

    while True:
        time.sleep(random.uniform(1, 2))

        html = page.content()
        current, total, links = parse_wgzimmer_search_results(html)
        listings.extend(links)
        logging.info(
            f"Parsed page {current} of {total} ({len(listings)} listings so far)"
        )

        progress.n = current if current else progress.n + 1
        progress.refresh()

        if current >= total:
            break

        btn = page.locator("div.skip a.next").first
        btn.click()
        page.wait_for_load_state("networkidle")

    progress.close()
    context.close()
    return listings


if __name__ == "__main__":
    logging.info("Entering main execution block.")

    export_path = os.path.join(SAVE_DIR, datetime.now(TIME_ZONE).isoformat() + ".json")
    os.makedirs(SAVE_DIR, exist_ok=True)

    try:
        with sync_playwright() as playwright:
            listings = main(playwright)
    except Exception as e:
        logging.exception(f"Could not parse pages {e}")
        sys.exit(1)

    logging.info(f"Succesfully found {len(listings)} new listings.")

    with open(export_path, "w") as f:
        json.dump(listings, f, indent=4)
