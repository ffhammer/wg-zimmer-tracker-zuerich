import argparse
import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import pytz
from browser_use import (
    ActionResult,
    Agent,
    Browser,
    BrowserConfig,
    BrowserContextConfig,
    Controller,
)
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

TIME_ZONE = pytz.timezone(os.environ["TIME_ZONE"])


# --- Main Parsing Function ---
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


load_dotenv()

LOG_FILE_PATH = "/app/app.log"  # Log file inside the container
SAVE_DIR = "/app/wg-zimmer-listings"
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

assert os.getenv("GEMINI_API_KEY"), "Missing GEMINI_API_KEY in environment."


all_contents: List[str] = []


class PageParam(BaseModel):
    page_number: int


controller = Controller()


@controller.action("Saves Page Content", param_model=PageParam)
async def save_content(params: PageParam, browser: Browser):
    page = await browser.get_current_page()
    content = await page.content()
    all_contents.append(content)
    return ActionResult(extracted_content="page content saved")


browser = Browser(
    config=BrowserConfig(
        headless=False,
        disable_security=False,
        keep_alive=True,
        new_context_config=BrowserContextConfig(
            keep_alive=True,
            disable_security=False,
        ),
    )
)


async def main(
    max_price: int,
    region: str,
    nur_unbefristete: bool,
    llm,
):
    global all_contents
    all_contents.clear()

    task = f"""
        First go to google.com and search 'www.wgzimmer.ch' manually.
        Then click on www.wgzimmer.ch and navigate to 'ein freies zimmer suchen'
        Now search for flats in {region} up to {max_price} CHF.
    """
    if nur_unbefristete:
        task += " Only show 'Nur Unbefristete' offers."
    task += " Skip through all and save all via save_content result. You don't need to scroll through them."
    task += " When you encounter adds or pop ups, close them."

    agent = Agent(
        task=task,
        llm=llm,
        browser=browser,
        controller=controller,
    )
    res = await agent.run()

    final_result: ActionResult = res.history[-1].result[-1]
    logging.info(f"Final Result: {final_result}")
    if not final_result.success:
        raise ValueError("Agent failed.")

    contents = list(all_contents)
    all_contents.clear()
    return contents


if __name__ == "__main__":
    logging.info("Entering main execution block.")

    parser = argparse.ArgumentParser()
    parser.add_argument("--max_price", type=int, default=800)
    parser.add_argument("--region", type=str, default="zürich stadt")
    parser.add_argument(
        "--gemini_model", type=str, default="gemini-2.5-flash-preview-04-17"
    )
    parser.add_argument(
        "--nur_unbefristete",
        action="store_true",
    )
    args = parser.parse_args()

    llm = ChatGoogleGenerativeAI(model=args.gemini_model)

    export_path = os.path.join(SAVE_DIR, datetime.now(TIME_ZONE).isoformat() + ".json")
    os.makedirs(SAVE_DIR, exist_ok=True)

    vals = asyncio.run(
        main(
            max_price=args.max_price,
            region=args.region,
            nur_unbefristete=args.nur_unbefristete,
            llm=llm,
        )
    )

    listings = []
    for idx, content in enumerate(vals):
        logging.info(f"Attempting to parse page {idx}")
        try:
            listings.extend(parse_wgzimmer_search_results(content)[-1])
        except Exception as e:
            logging.error(f"Failed to parse page {idx}: {e}")

    with open(export_path, "w") as f:
        json.dump(listings, f, indent=4)

    logging.info(f"\n\n{'-' * 50}\nSuccessfully finished job!{'-' * 50}\n\n")
