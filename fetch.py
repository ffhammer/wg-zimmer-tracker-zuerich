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
PERSISTENT_CONTEXT_FILE = "cookies.json"


class CapthaError(Exception):
    pass


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
            # args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
        )
    except PlaywrightError as e:
        logging.error(f"Failed to launch browser: {e}")
        raise  # Re-raise the exception to stop the script

    context_options = {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",  # Keep UA updated
        "viewport": {"width": 1920, "height": 1080},
        "locale": "de-CH",
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
        time.sleep(2)
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

        # raise # Uncomment to make sorting failure critical


def scrape_results_pages(page, log_dir) -> list[Listing]:
    """Iterates through result pages, takes screenshots, and saves HTML content."""
    logging.info("Starting scraping results pages...")
    all_listings = []
    page_num = 1
    total_pages = None  # Keep track of total pages discovered

    while True:
        logging.info(f"--- Processing Page {page_num} ---")
        # It's crucial to wait *before* getting content, especially on subsequent pages
        # Let's add a more specific wait here if page_num > 1
        if page_num > 1:
            # Wait for the pagination indicator to show the *current* page number
            expected_pagination_text = f"Seite {page_num}/"
            pagination_selector = (
                f'div.skip span.counter:has-text("{expected_pagination_text}")'
            )
            try:
                logging.info(f"Waiting for pagination indicator for page {page_num}...")
                page.wait_for_selector(
                    pagination_selector, state="visible", timeout=30000
                )
                logging.info(f"Pagination indicator for page {page_num} confirmed.")
                # Add a small buffer delay for content rendering after pagination update
                random_delay(1000, 2500)
            except PlaywrightTimeoutError:
                logging.error(
                    f"Timeout waiting for page {page_num} content/pagination update. Stopping pagination."
                )
                take_screenshot(page, f"error_page_load_timeout_p{page_num}", log_dir)
                break  # Stop if the expected page doesn't seem to load

        # Take screenshot *after* ensuring the page is hopefully correct
        take_screenshot(page, f"page_{page_num}", log_dir)

        # Get content *after* waiting/confirming
        try:
            html_content = page.content()
            # Optional: Save HTML for debugging specific pages
            # with open(os.path.join(log_dir, f"page_{page_num}_content.html"), "w") as f:
            #     f.write(html_content)
        except PlaywrightError as e:
            logging.error(f"Failed to get page content for page {page_num}: {e}")
            take_screenshot(page, f"error_get_content_p{page_num}", log_dir)
            break  # Cannot proceed without content

        # Parse the confirmed content
        current_page_parsed, total_pages_parsed, listings = (
            parse_wgzimmer_search_results(html_content=html_content)
        )

        # Update total_pages if discovered
        if total_pages_parsed is not None:
            total_pages = total_pages_parsed

        # Sanity check: Does the parsed page number match our expected page number?
        if current_page_parsed is not None and current_page_parsed != page_num:
            logging.warning(
                f"Parsed page number ({current_page_parsed}) does not match expected page number ({page_num}). Content might be stale."
            )
            # Decide how to handle: break, retry, or continue cautiously? Let's break for safety.
            take_screenshot(page, f"warning_page_mismatch_p{page_num}", log_dir)
            break

        if not listings and page_num > 1:
            logging.warning(
                f"No listings found on page {page_num}, content might be wrong or page empty."
            )
            # Optionally break here too if empty pages are unexpected after page 1

        all_listings.extend(listings)  # Use extend, no need for .copy() here
        logging.info(
            f"Parsed results: current = {current_page_parsed}, total = {total_pages}, len(listings) = {len(listings)}"
        )

        # Check if we are on the last page (using the potentially updated total_pages)
        if total_pages is not None and page_num >= total_pages:
            logging.info(
                f"Reached last page ({page_num}/{total_pages}) based on parser."
            )
            break
        if (
            current_page_parsed is not None
            and total_pages_parsed is not None
            and current_page_parsed >= total_pages_parsed
        ):
            logging.info(
                f"Reached last page ({current_page_parsed}/{total_pages_parsed}) based on current parse."
            )
            break

        # --- Find and Click Next ---
        next_button = page.locator(
            'a:has-text("Next"), a:has-text("Weiter"), a:has-text("Nächste")'
        ).first

        try:
            # Check visibility first, then disabled state
            is_visible = next_button.is_visible(timeout=5000)
            if not is_visible:
                logging.info(
                    f"'Next' button not visible on page {page_num}. Assuming end of results."
                )
                break

            is_disabled = next_button.is_disabled(
                timeout=1000
            )  # Shorter timeout for disabled check

            if not is_disabled:
                logging.info(
                    f"Found active 'Next' button on page {page_num}. Clicking for page {page_num + 1}..."
                )
                next_button.click()
                page_num += (
                    1  # Increment page number *after* clicking for the next page
                )
                # The wait for the *new* page content will happen at the start of the next loop iteration
            else:
                logging.info(
                    f"'Next' button is disabled on page {page_num}. Assuming end of results."
                )
                break  # Exit the loop

        except PlaywrightTimeoutError:
            logging.warning(
                f"Timeout checking 'Next' button state on page {page_num}. Assuming end of results."
            )
            take_screenshot(page, f"warning_next_button_timeout_p{page_num}", log_dir)
            break
        except PlaywrightError as e:
            logging.info(
                f"Could not find or interact with 'Next' button on page {page_num}, assuming end of results. Error: {e}"
            )
            take_screenshot(page, f"info_next_button_error_p{page_num}", log_dir)
            break

    logging.info(f"Finished scraping. Total unique listings found: {len(all_listings)}")
    # Optional: Add de-duplication just in case, based on URL
    seen_urls = set()
    unique_listings = []
    for listing in all_listings:
        if listing.url not in seen_urls:
            unique_listings.append(listing)
            if listing.url:
                seen_urls.add(listing.url)
    if len(unique_listings) != len(all_listings):
        logging.warning(
            f"De-duplicated listings: {len(all_listings)} -> {len(unique_listings)}"
        )

    return unique_listings  # Return unique list


def fetch_listings(
    headless: bool,
    log_dir: str,
    min_price: int,
    max_price: int,
    record_video=True,
    region: str = "zurich-stadt",
) -> list[Listing]:
    """Main function to orchestrate the scraping process."""

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
                log_dir, p, headless=headless, record_video=record_video
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
            listings = scrape_results_pages(page, log_dir)
            logging.info("Scraping process completed successfully.")
            take_screenshot(page, "99_final_page_state", log_dir)
            logging.info("--- WG Zimmer Scraper Finished ---")

            return listings

    except PlaywrightTimeoutError as e:
        logging.error(f"A timeout error occurred: {e}")
        if page:
            take_screenshot(page, "error_timeout_final", log_dir=log_dir)
        raise e
    except PlaywrightError as e:
        logging.error(f"A Playwright error occurred: {e}")
        if page:
            take_screenshot(page, "error_playwright_final")
        raise e
    except CapthaError as e:
        raise e
    except Exception as e:
        logging.exception(f"An unexpected error occurred: {e}")
        raise e
