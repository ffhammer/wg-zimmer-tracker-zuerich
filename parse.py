import re
from datetime import datetime
from typing import List, Tuple, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag
from pydantic import BaseModel, Field, HttpUrl, ValidationError


# --- Pydantic Model Definition ---
# (Assuming you have pydantic installed: pip install pydantic)
class Listing(BaseModel):
    aufgegeben_datum: Optional[datetime] = Field(
        None, description="das datum wo das inserat aufgegeb wurde"
    )
    datum_ab_frei: Optional[datetime] = Field(
        None, description="das datum ab dem das inserat frei ist"
    )
    miete: Optional[float] = Field(None, description="miete in schweizer franken")
    adresse: Optional[str] = Field(None, description="einfach ganzer adress string")
    url: Optional[HttpUrl] = Field(None, description="die url zu dem specifischen post")
    img_url: Optional[HttpUrl] = Field(None, description="URL des Vorschaubildes")


# --- Helper Function for Safe Parsing ---
def safe_find_text(
    tag: Optional[Tag], selector: str, strip: bool = True
) -> Optional[str]:
    """Safely find a sub-tag and return its stripped text."""
    if not tag:
        return None
    found_tag = tag.select_one(selector)
    if found_tag:
        text = found_tag.get_text(strip=strip)
        return text if text else None
    return None


def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse date string in DD.MM.YYYY format."""
    if not date_str:
        return None
    # Sometimes there's extra text like '<br>' or whitespace
    date_str_cleaned = date_str.split("<br>")[0].strip()
    try:
        # Locale might affect month parsing if names were used, but DD.MM.YYYY is safe
        return datetime.strptime(date_str_cleaned, "%d.%m.%Y")
    except ValueError:
        print(f"Warning: Could not parse date: {date_str}")
        return None


def parse_float(float_str: Optional[str]) -> Optional[float]:
    """Parse float string, removing potential thousand separators."""
    if not float_str:
        return None
    try:
        # Remove potential thousand separators like '.' or "'"
        cleaned_str = float_str.replace(".", "").replace("'", "").strip()
        return float(cleaned_str)
    except ValueError:
        print(f"Warning: Could not parse float: {float_str}")
        return None


# --- Main Parsing Function ---
def parse_wgzimmer_search_results(
    html_content: str, base_url: str = "https://www.wgzimmer.ch"
) -> Tuple[Optional[int], Optional[int], List[Listing]]:
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
    listings: List[Listing] = []

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
            listing_data = {}
            try:
                # --- Extract URL ---
                link_tag = item.select_one("a")
                relative_url = link_tag["href"] if link_tag else None
                listing_data["url"] = (
                    urljoin(base_url, relative_url) if relative_url else None
                )

                # --- Extract Dates ---
                aufgegeben_str = safe_find_text(item, "div.create-date strong")
                listing_data["aufgegeben_datum"] = parse_date(aufgegeben_str)

                frei_ab_str = safe_find_text(item, "span.from-date strong")
                listing_data["datum_ab_frei"] = parse_date(frei_ab_str)

                # --- Extract Miete ---
                miete_str = safe_find_text(item, "span.cost strong")
                listing_data["miete"] = parse_float(miete_str)

                # --- Extract Adresse ---
                # The address details are within span.thumbState inside span.state.image
                adresse_tag = item.select_one("span.state.image span.thumbState")
                if adresse_tag:
                    # Get all text, including bold city/area and description lines
                    adresse_parts = [
                        part.strip() for part in adresse_tag.stripped_strings
                    ]
                    listing_data["adresse"] = (
                        " ".join(adresse_parts) if adresse_parts else None
                    )
                else:
                    listing_data["adresse"] = None

                # --- Extract Image URL ---
                img_tag = item.select_one("span.thumb img")
                relative_img_url = (
                    img_tag["src"] if img_tag and "src" in img_tag.attrs else None
                )
                # Image URLs seem absolute already on the site
                listing_data["img_url"] = (
                    relative_img_url
                    if relative_img_url != "/docroot/img.wgzimmer.ch/loading.gif"
                    else None
                )

                # --- Create Listing Object ---
                try:
                    listing = Listing(**listing_data)
                    listings.append(listing)
                except ValidationError as e:
                    print(
                        f"Warning: Validation failed for listing data: {listing_data}\nError: {e}"
                    )
                except Exception as e:
                    print(
                        f"Warning: Could not create Listing object for data: {listing_data}\nError: {e}"
                    )

            except Exception as e:
                # Catch any unexpected error during parsing a single list item
                print(f"Warning: Failed to parse a list item. Error: {e}")
                # Optionally log the problematic item HTML: print(item.prettify())
                continue  # Skip to the next item

    return current_page, total_pages, listings


# --- Example Usage ---
if __name__ == "__main__":
    html = open("/Users/felix/Desktop/wohnung/output/website_4.html").read()
    parse_wgzimmer_search_results(html_content=html)[-1]
