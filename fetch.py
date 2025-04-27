import time
import random
import logging
import os
from parse import parse_wgzimmer_search_results, Listing
from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError,
)

# --- Configuration ---
TARGET_URL = "https://www.wgzimmer.ch/wgzimmer/search/mate.html"
PERSISTENT_CONTEXT_FILE = "good.json"


class CapthaError(Exception):
    pass


# --- Helper Functions ---
def setup_logging(log_file):
    """Configures logging to file and console."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, mode="w"),  # 'w' to overwrite log each run
            logging.StreamHandler(),
        ],
    )
    # Suppress noisy playwright logs if desired
    logging.getLogger("playwright").setLevel(logging.WARNING)


def random_delay(min_ms=300, max_ms=800):
    """Adds a random delay in seconds."""
    delay = random.uniform(min_ms / 1000.0, max_ms / 1000.0)
    logging.debug(f"Waiting for {delay:.2f} seconds...")
    time.sleep(delay)


def take_screenshot(page, name, log_dir):
    """Takes a screenshot and saves it to the logs directory."""
    path = os.path.join(log_dir, f"{name}.png")
    try:
        page.screenshot(path=path, full_page=True)
        logging.info(f"Screenshot saved: {path}")
    except PlaywrightError as e:
        logging.error(f"Failed to take screenshot {name}: {e}")


# --- Core Logic Functions ---


def initialize_browser_context(
    log_dir,
    p,
    headless=False,
    proxy_settings=None,
    record_video=True,
):
    """Launches the browser and creates a context (new or from state)."""
    logging.info("Launching browser...")
    try:
        browser = p.chromium.launch(
            headless=headless,
            slow_mo=50,
            proxy=proxy_settings,
        )
    except PlaywrightError as e:
        logging.error(f"Failed to launch browser: {e}")
        raise  # Re-raise the exception to stop the script

    context_options = {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",  # Keep UA updated
        "viewport": {"width": 1920, "height": 1080},
        "locale": "de-CH",  # More specific locale
        "timezone_id": "Europe/Zurich",
    }
    if record_video:
        context_options["record_video_dir"] = log_dir
        logging.info(f"Video recording enabled. Saving to: {log_dir}")

    try:
        context = browser.new_context(
            storage_state=PERSISTENT_CONTEXT_FILE, **context_options
        )
        logging.info(f"Loaded context from {PERSISTENT_CONTEXT_FILE}")
    except FileNotFoundError:
        logging.warning(
            f"No previous context file found at {PERSISTENT_CONTEXT_FILE}. Creating new context."
        )
        context = browser.new_context(**context_options)
    except Exception as e:
        logging.error(f"Error loading context from file, creating new: {e}")
        context = browser.new_context(**context_options)

    return browser, context


def navigate_and_prepare_search(page, url, log_dir):
    """Navigates to the target URL and handles potential pre-filled search."""
    logging.info(f"Navigating to {url}...")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        logging.info("Page loaded initially.")
        take_screenshot(page, "01_initial_page", log_dir)
        random_delay(2000, 4000)  # Wait for dynamic elements

        # Check if a search is already saved (indicated by "Neue Suche" button)
        neue_suche_button = page.locator('a:has-text("Neue Suche")').first
        # Check if the button exists *and* if the search form is *not* visible initially
        # This distinguishes the results page from the initial search page
        form_selector = "form#searchMateForm"
        form_is_visible = page.locator(form_selector).is_visible()

        if neue_suche_button.is_visible() and not form_is_visible:
            logging.info("Detected previous search results. Clicking 'Neue Suche'...")
            neue_suche_button.click()
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            logging.info("Navigated to the main search page.")
            take_screenshot(page, "01a_navigated_to_new_search", log_dir)
            random_delay()
        else:
            logging.info("On the main search page or form is already visible.")

    except PlaywrightTimeoutError:
        logging.error(f"Timeout navigating to {url} or finding 'Neue Suche'.")
        take_screenshot(page, "error_navigation_timeout", log_dir)
        raise
    except PlaywrightError as e:
        logging.error(f"Playwright error during navigation/preparation: {e}")
        take_screenshot(page, "error_navigation_generic", log_dir)
        raise


def fill_search_form(page, min_price, max_price, region, log_dir):
    """Fills the search form fields."""
    logging.info("Filling the search form...")
    form_selector = "form#searchMateForm"
    try:
        page.wait_for_selector(form_selector, state="visible", timeout=20000)

        # Optional: Click search term input if needed (sometimes helps focus)
        # query_input = page.locator(f'{form_selector} input[name="query"]')
        # query_input.click()
        # random_delay(100, 300)

        # Price Min
        logging.info(f"Setting min price: {min_price}")
        page.locator(f'{form_selector} select[name="priceMin"]').select_option(
            min_price
        )
        random_delay()

        # Price Max
        logging.info(f"Setting max price: {max_price}")
        page.locator(f'{form_selector} select[name="priceMax"]').select_option(
            max_price
        )
        random_delay()

        # Region
        logging.info(f"Setting region: {region}")
        page.locator(f'{form_selector} select[name="wgState"]').select_option(region)
        random_delay()

        # Permanent ('Nur Unbefristete')
        logging.info("Selecting 'Nur Unbefristete'")
        page.locator(f'{form_selector} input[name="permanent"][value="true"]').check()
        random_delay()

        take_screenshot(page, "02_form_filled", log_dir=log_dir)
        logging.info("Search form filled.")

    except PlaywrightTimeoutError:
        logging.error("Timeout waiting for search form elements.")
        take_screenshot(page, "error_form_fill_timeout", log_dir=log_dir)
        raise
    except PlaywrightError as e:
        logging.error(f"Playwright error filling the form: {e}")
        take_screenshot(page, "error_form_fill_generic", log_dir=log_dir)
        raise


def submit_search_and_verify(page, log_dir):
    """Submits the form and checks for CAPTCHA or successful results page."""
    logging.info("Submitting search form...")
    form_selector = "form#searchMateForm"
    submit_button_selector = f'{form_selector} input[type="button"][value="Suchen"]'

    try:
        submit_button = page.locator(submit_button_selector)
        page.wait_for_selector(submit_button_selector, state="visible", timeout=10000)

        # Optional: Simulate hovering
        box = submit_button.bounding_box()
        if box:
            page.mouse.move(
                box["x"] + box["width"] / 2 + random.uniform(-5, 5),
                box["y"] + box["height"] / 2 + random.uniform(-3, 3),
                steps=random.randint(5, 15),
            )
            random_delay(400, 900)

        logging.info("Clicking submit button...")
        submit_button.click()

        # --- Verification ---
        # IMPORTANT: Wait long enough for the page to potentially redirect or load results.
        # Using a fixed sleep here is not ideal, but sometimes necessary if
        # wait_for_load_state or wait_for_url isn't reliable after form submission.
        # Consider adjusting this value based on observation.
        logging.info("Waiting after submit (10s)...")
        time.sleep(10)
        take_screenshot(page, "03_after_submit", log_dir)

        # 1. Check for CAPTCHA
        page_content_lower = page.content().lower()
        if "Das Verarbeiten der Anfrage".lower() in page_content_lower:
            # More specific checks might be needed depending on the CAPTCHA implementation
            logging.error("CAPTCHA detected after form submission.")
            take_screenshot(page, "error_captcha_detected", log_dir)
            raise CapthaError("CAPTCHA detected")  # Raise specific error

        # 2. Check for success (e.g., presence of "Neue Suche" button on results page)
        #    We expect the "Neue Suche" button to be visible again on the results page.
        neue_suche_button_results = page.locator('a:has-text("Neue Suche")').first
        if not neue_suche_button_results.is_visible(
            timeout=5000
        ):  # Short timeout check
            # Also check for common result list indicators if needed
            logging.error(
                "Could not confirm results page loaded successfully (missing 'Neue Suche' button)"
            )
            raise ValueError("not on seach page ladnedn")
        else:
            logging.info("Successfully submitted form and results page seems loaded.")

    except PlaywrightTimeoutError:
        logging.error(
            "Timeout waiting for submit button or during post-submit verification."
        )
        take_screenshot(page, "error_submit_timeout", log_dir)
        raise
    except PlaywrightError as e:
        logging.error(f"Playwright error during form submission or verification: {e}")
        take_screenshot(page, "error_submit_generic", log_dir)
        raise


def sort_results(page, log_dir):
    """Sorts the results by date (oldest first)."""
    logging.info("Sorting results by 'Ab dem' (oldest first)...")
    sort_link_selector = 'a:has-text("Ab dem")'
    try:
        sort_link = page.locator(sort_link_selector)
        # Click twice to sort ascending (oldest first)
        logging.info("Clicking 'Ab dem' (1st time)...")
        sort_link.click()
        page.wait_for_load_state(
            "domcontentloaded", timeout=20000
        )  # Wait for potential reload
        random_delay(1000, 2000)
        take_screenshot(page, "04a_sorted_desc", log_dir=log_dir)

        logging.info("Clicking 'Ab dem' (2nd time)...")
        # Re-locate the element in case the page reloaded fully
        page.locator(sort_link_selector).click()
        page.wait_for_load_state("domcontentloaded", timeout=20000)  # Wait again
        random_delay(1000, 2000)
        take_screenshot(page, "04b_sorted_asc", log_dir=log_dir)
        logging.info("Results sorted.")
    except PlaywrightTimeoutError:
        logging.error("Timeout waiting for sort link or page reload during sorting.")
        take_screenshot(page, "error_sort_timeout", log_dir=log_dir)
        # Decide if this is critical - maybe continue without sorting?
        # raise # Uncomment to make sorting failure critical
    except PlaywrightError as e:
        logging.error(f"Playwright error during sorting: {e}")
        take_screenshot(page, "error_sort_generic", log_dir=log_dir)
        # raise # Uncomment to make sorting failure critical


def scrape_results_pages(page, log_dir) -> list[Listing]:
    """Iterates through result pages, takes screenshots, and saves HTML content."""
    logging.info("Starting scraping results pages...")
    all_listings = []
    page_num = 1

    while True:
        logging.info(f"--- Processing Page {page_num} ---")
        random_delay(1500, 3000)  # Spend some time on the page

        # Take screenshot of the current page
        take_screenshot(page, f"page_{page_num}", log_dir)

        # Append HTML content to the list

        html_content = page.content()
        current_pages, total_pags, listings = parse_wgzimmer_search_results(
            html_content=html_content
        )
        all_listings.extend(listings)

        if current_pages == total_pags:
            break

        # Using :near() might be fragile, prefer a more direct selector if possible
        # Let's try a common pattern: a link with text "Next" or similar, often within pagination controls
        next_button = page.locator(
            'a:has-text("Next"), a:has-text("Weiter"), a:has-text("Nächste")'
        ).first
        # Alternative: Look for a link that might contain a specific class or structure
        # next_button = page.locator('.pagination a.next') # Example if classes exist

        try:
            is_disabled = next_button.is_disabled(
                timeout=5000
            )  # Check if disabled attribute exists
            is_visible = next_button.is_visible()

            if is_visible and not is_disabled:
                logging.info(
                    f"Found 'Next' button for page {page_num + 1}. Clicking..."
                )
                next_button.click()
                # Wait for navigation/content update after clicking 'Next'
                page.wait_for_load_state("domcontentloaded", timeout=30000)
                page_num += 1
            else:
                logging.info("No more 'Next' pages found or button is disabled.")
                break  # Exit the loop

        except PlaywrightTimeoutError:
            logging.warning(
                f"Timeout checking 'Next' button state on page {page_num}. Assuming end of results."
            )
            take_screenshot(page, f"warning_next_button_timeout_p{page_num}", log_dir)
            break
        except PlaywrightError as e:
            # This might happen if the locator doesn't find the element at all
            logging.info(
                f"Could not find 'Next' button using selectors, assuming end of results. Error: {e}"
            )
            take_screenshot(page, f"info_next_button_not_found_p{page_num}", log_dir)
            break  # Exit loop if element not found

    logging.info(f"Finished scraping {len(all_listings)} pages.")
    return all_listings


def fetch_listings(
    headless: bool,
    log_dir: str,
    min_price: int,
    max_price: int,
    region: str = "zurich-stadt",
) -> list[Listing]:
    """Main function to orchestrate the scraping process."""

    os.makedirs(
        log_dir,
        exist_ok=True,
    )
    LOG_FILE = os.path.join(log_dir, "scraping.log")
    setup_logging(log_file=LOG_FILE)

    if min_price not in range(200, 1550, 50):
        raise ValueError("invalid min_price")
    if max_price not in range(200, 1550, 50):
        raise ValueError("invalid max_price")

    logging.info("--- Starting WG Zimmer Scraper ---")

    browser = None
    context = None
    page = None
    try:
        with sync_playwright() as p:
            browser, context = initialize_browser_context(
                log_dir, p, headless=headless, record_video=True
            )
            page = context.new_page()

            navigate_and_prepare_search(page, TARGET_URL, log_dir)
            fill_search_form(
                page,
                min_price=str(min_price),
                max_price=str(max_price),
                region=region,
                log_dir=log_dir,
            )
            submit_search_and_verify(page, log_dir)
            sort_results(page, log_dir)  # Sort after successful submission
            listings = scrape_results_pages(page, log_dir)
            logging.info("Scraping process completed successfully.")
            take_screenshot(page, "99_final_page_state", log_dir)
            logging.info("--- WG Zimmer Scraper Finished ---")

            return listings

    except PlaywrightTimeoutError as e:
        logging.error(f"A timeout error occurred: {e}")
        if page:
            take_screenshot(page, "error_timeout_final", log_dir=log_dir)
    except PlaywrightError as e:
        logging.error(f"A Playwright error occurred: {e}")
        if page:
            take_screenshot(page, "error_playwright_final")
    except Exception as e:
        logging.exception(
            f"An unexpected error occurred: {e}"
        )  # Use logging.exception to include traceback
        if page:
            take_screenshot(page, "error_unexpected_final")
    finally:
        if context:
            try:
                context.close()
                logging.info("Context closed.")
            except PlaywrightError as e:
                logging.error(
                    f"Playwright error saving context state or closing context: {e}"
                )
            except Exception as e:
                logging.error(f"Could not save context state: {e}")
