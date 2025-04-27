from fetch import fetch_listings, CapthaError
import time

try:
    res = fetch_listings(
        headless=False, log_dir="logs/first_run", min_price=200, max_price=800
    )
except CapthaError:
    print("capthca error sleeping for 20 seconds and trying again")
    time.sleep(20)
    res = fetch_listings(
        headless=False, log_dir="logs/first_run", min_price=200, max_price=800
    )

print("results")
print(res)
