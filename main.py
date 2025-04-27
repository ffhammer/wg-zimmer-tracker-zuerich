from fetch import fetch_listings, CapthaError
import time
import logging
import playwright
import os


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


LOG_DIR = "logs/second"

os.makedirs(
    LOG_DIR,
    exist_ok=True,
)
LOG_FILE = os.path.join(LOG_DIR, "scraping.log")
setup_logging(log_file=LOG_FILE)

try:
    res = fetch_listings(headless=True, log_dir=LOG_DIR, min_price=200, max_price=800)
except CapthaError:
    print("capthca error sleeping for 20 seconds and trying again")
    time.sleep(20)
    res = fetch_listings(headless=True, log_dir=LOG_DIR, min_price=200, max_price=800)

print("results")
print(res)
