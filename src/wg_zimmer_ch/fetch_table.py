import math
import os
import random
import re
import time
from datetime import date, datetime
from typing import List, Optional, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from loguru import logger
from playwright.sync_api import Locator, Page, sync_playwright

path_to_extension = "uBlock0.chromium"

assert os.path.exists(path_to_extension)
user_data_dir = "chromium-user-data-dir"


def inject_fake_cursor(page: Page) -> None:
    page.add_script_tag(
        content="""
      (function(){
        const style = document.createElement('style');
        style.textContent = `
          #fake-cursor {
            width: 20px; height: 20px;
            background: url('data:image/svg+xml;utf8,\
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">\
                <circle cx="10" cy="10" r="5" fill="red"/></svg>') no-repeat center;
            position: absolute; pointer-events: none; z-index: 999999;
          }
        `;
        document.head.appendChild(style);
        const cursor = document.createElement('div');
        cursor.id = 'fake-cursor';
        document.body.appendChild(cursor);
        window.addEventListener('mousemove', e => {
          cursor.style.left = e.clientX + 'px';
          cursor.style.top  = e.clientY + 'px';
        });
      })();
    """
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


def random_mouse_move(
    page: Page,
    start: tuple[int, int],
    end: tuple[int, int],
    steps: int = 30,
    minor_axis_ratio: float = 0.4,
) -> None:
    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    dist = math.hypot(dx, dy)
    ux, uy = dx / dist, dy / dist
    vx, vy = -uy, ux
    a = dist / 2
    b = a * minor_axis_ratio
    mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2

    for i in range(steps + 1):
        t = i / steps
        theta = math.pi * (1 - t)
        px = mid_x + ux * a * math.cos(theta) + vx * b * math.sin(theta)
        py = mid_y + uy * a * math.cos(theta) + vy * b * math.sin(theta)
        page.mouse.move(px, py)


def move_to_and_click(
    page: Page,
    locator: Locator,
    start: tuple[float, float],
) -> tuple[float, float]:
    bb = locator.bounding_box()
    pos = (bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)

    random_mouse_move(page, start, pos)
    page.mouse.click(*pos)

    return pos


def last_aufgegeben_date(html_content: str) -> Optional[date]:
    soup = BeautifulSoup(html_content, "html.parser")
    items = soup.select(
        "ul#search-result-list li.search-result-entry.search-mate-entry"
    )
    if not items:
        return None
    last = items[-1]
    strong = last.select_one("div.create-date strong")
    if not strong:
        return None
    text = strong.get_text(strip=True)  # e.g. "18.5.2025"
    return datetime.strptime(text, "%d.%m.%Y").date()


def open_listings_page(
    parse_wgzimmer_search_results, random_mouse_move, move_to_and_click, page
):
    logger.info("opening page")
    page.goto("https://www.wgzimmer.ch/wgzimmer/search/mate.html")
    inject_fake_cursor(page)
    # inject_fake_cursor(page)

    logger.info("initial random movements")
    time.sleep(random.uniform(1.5, 3.5))
    w, h = page.viewport_size["width"], page.viewport_size["height"]
    mouse_pos = (random.uniform(w * 0.4, w * 0.7), random.uniform(h * 0.4, h * 0.7))
    random_mouse_move(
        page,
        (0, 0),
        mouse_pos,
    )

    # Click th  e correct 'Neue Suche' (in result-navigation)
    if (None, None, []) != parse_wgzimmer_search_results(page.content()):
        logger.info("We are on results page, going to new search")
        time.sleep(random.uniform(1.5, 3.5))
        button = page.locator(
            "div.result-navigation a.search", has_text="Neue Suche"
        ).nth(0)
        mouse_pos = move_to_and_click(page, button, mouse_pos)

    time.sleep(random.uniform(1.5, 3.5))
    page.mouse.wheel(0, 100)
    time.sleep(0.2)

    zürich_stadt = page.locator("span.stateShortcut[data-state='zurich-stadt']")
    logger.info("moving to zürich stadt")
    mouse_pos = move_to_and_click(page, zürich_stadt, mouse_pos)

    time.sleep(random.uniform(0.5, 1.5))
    # scroll to and click Suchen
    suchen = page.locator("input[type='button'][value='Suchen']")
    logger.info("moving to suchen")
    mouse_pos = move_to_and_click(page, suchen, mouse_pos)


def extract_listings(page, last_update_date):
    # time.sleep(random.uniform(3, 5))
    time.sleep(10)
    if not any(parse_wgzimmer_search_results(page.content())):
        raise RuntimeError("Not on target page")

    # click "Ab dem" ascending
    page.locator('a.sort[href*="orderDir=asc"]:has-text("Aufgegeben")').click()
    # optional wait
    time.sleep(random.uniform(1, 2))
    # click "Aufgegeben" descending
    page.locator('a.sort[href*="orderDir=desc"]:has-text("Aufgegeben")').click()
    time.sleep(random.uniform(1, 2))

    listings: set[str] = set()

    while True:
        html = page.content()
        current_date = last_aufgegeben_date(html)
        current, total, links = parse_wgzimmer_search_results(html)
        listings.update(links)

        logger.info(
            f"Parsed page {current} with last update date {current_date}. ({len(listings)} listings so far)."
        )

        if current_date < last_update_date or current >= total:
            break

        # move ot next pate
        btn = page.locator("div.skip a.next").first
        btn.click()
        time.sleep(random.uniform(1, 2))
    return list(listings)


def fetch_table(last_update_date: date):
    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir,
                headless=False,
                args=[
                    f"--disable-extensions-except={path_to_extension}",
                    f"--load-extension={path_to_extension}",
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-setuid-sandbox",
                    "--disable-gpu",
                    "--window-size=1920,1080",
                    "--disable-features=IsolateOrigins,site-per-process",
                ],
            )
            page = context.pages[0]

            open_listings_page(
                parse_wgzimmer_search_results,
                random_mouse_move,
                move_to_and_click,
                page,
            )

            listings = extract_listings(page, last_update_date)
            logger.success("We made it (:")
            return listings
    except Exception:
        logger.exception("Failure")
