# app.py
import streamlit as st
import pandas as pd
import json
import os
import threading
import queue
import time
from datetime import datetime, timedelta

# Lokale Module importieren
from models import ListingScraped, ListingStored
import database
from src.sdk import run_wgzimmer_fetcher, DockerComposeRunnerError
from typing import Literal, List


# --- Konstanten & Konfiguration ---
LISTINGS_DIR = "listings"
OUTPUT_FILENAME = "fetched_listings.jsonl"
OUTPUT_FILEPATH = os.path.join(LISTINGS_DIR, OUTPUT_FILENAME)
LOG_QUEUE = queue.Queue()  # Queue für Thread-Kommunikation (Logs, Status)

# --- Hilfsfunktionen ---


def parse_output_file(filepath: str) -> List[ListingScraped]:
    """Liest die JSONL-Datei und gibt eine deduplizierte Liste von Listings zurück."""
    listings = []
    seen_urls = set()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    listing = ListingScraped(**data)
                    if listing.url:
                        url_str = str(listing.url)
                        if url_str not in seen_urls:
                            listings.append(listing)
                            seen_urls.add(url_str)
                        else:
                            st.sidebar.warning(f"Duplicate URL skipped: {url_str}")
                except json.JSONDecodeError:
                    st.sidebar.error(f"Skipping invalid JSON line: {line.strip()}")
                except Exception as e:  # Catch Pydantic validation errors etc.
                    st.sidebar.error(
                        f"Error parsing listing from line: {e} - Data: {line.strip()}"
                    )
    except FileNotFoundError:
        st.sidebar.error(f"Output file not found: {filepath}")
    return listings


def process_fetched_data():
    """Verarbeitet die neu gefetchten Daten: Parsen, DB-Update, Notifications."""
    st.session_state.notifications = []  # Clear previous notifications
    scraped_listings = parse_output_file(OUTPUT_FILEPATH)

    if not scraped_listings:
        st.session_state.notifications.append(
            ("error", "No valid listings found in the output file.")
        )
        return

    scraped_urls = {str(l.url) for l in scraped_listings if l.url}

    # Update DB
    try:
        new_count, updated_count = database.upsert_listings(scraped_listings)
        deleted_count = database.mark_listings_as_deleted(scraped_urls)
        st.session_state.notifications.append(
            (
                "success",
                f"Fetch complete! {new_count} new, {updated_count} updated, {deleted_count} marked as deleted.",
            )
        )
    except Exception as e:
        st.session_state.notifications.append(
            ("error", f"Error updating database: {e}")
        )
        st.exception(e)  # Log full exception to Streamlit

    # Trigger reload of listing display
    st.session_state.listings_dirty = True


def fetch_thread_func():
    """Führt den Fetcher in einem separaten Thread aus."""
    global LOG_QUEUE
    try:
        LOG_QUEUE.put(("status", "starting"))  # Signal start
        LOG_QUEUE.put(("log", "--- Starting Docker container ---"))
        # Der SDK call ist ein Generator
        sdk_generator = run_wgzimmer_fetcher(export_filename=OUTPUT_FILENAME)
        print("yes")
        for log_line in sdk_generator:
            print(log_line)
            LOG_QUEUE.put(("log", log_line))  # Send logs via queue

        # Wenn der Generator ohne Exception endet -> Erfolg
        LOG_QUEUE.put(("log", "--- Docker container finished successfully ---"))
        LOG_QUEUE.put(("status", "processing"))  # Signal data processing start
        process_fetched_data()  # Process data after successful run
        LOG_QUEUE.put(("status", "finished"))  # Signal successful completion

    except DockerComposeRunnerError as e:
        error_message = f"--- Fetcher Error: {e} ---"
        LOG_QUEUE.put(("log", error_message))
        LOG_QUEUE.put(("error", error_message))  # Signal error
        LOG_QUEUE.put(("status", "error"))  # Signal error state
    except Exception as e:
        error_message = f"--- Unexpected Error in Fetch Thread: {e} ---"
        LOG_QUEUE.put(("log", error_message))
        st.exception(e)  # Log stack trace to Streamlit console/logs
        LOG_QUEUE.put(("error", error_message))
        LOG_QUEUE.put(("status", "error"))
    finally:
        # Ensure a final status is always sent if not 'finished' or 'error'
        pass  # Status should be set above


def start_fetch():
    """Startet den Fetch-Thread."""
    if not st.session_state.fetching:
        st.session_state.fetching = True
        st.session_state.logs = ["--- Initializing Fetch ---"]  # Reset logs
        st.session_state.notifications = [("info", "Starting fetch process...")]
        st.session_state.fetch_error = None

        thread = threading.Thread(target=fetch_thread_func, daemon=True)
        thread.start()
        # Optional: Start a mechanism to check the queue periodically while fetching
        # This is complex in Streamlit. Simpler: Process queue after button click.


def update_db_status_callback(listing_id: str, field: Literal["gesehen", "gemerkt"]):
    """Callback für die Checkboxen 'gesehen' und 'gemerkt'."""
    key = f"{field}_{listing_id}"
    new_value = st.session_state[key]  # Get the new value from the widget
    st.write(f"Callback for {key} triggered, new value: {new_value}")  # Debug
    success = database.update_listing_user_status(
        url=listing_id, field=field, value=new_value
    )
    if success:
        # Mark listings as dirty to trigger potential refiltering/display update
        st.session_state.listings_dirty = True
        st.toast(f"Status '{field}' für {listing_id[:30]}... aktualisiert!", icon="✅")
        # Force immediate small update if needed, but usually handled by Streamlit rerun
        # st.rerun()
    else:
        st.toast(
            f"Fehler beim Aktualisieren von '{field}' für {listing_id[:30]}...",
            icon="❌",
        )
        # Revert checkbox state in UI if DB update failed (tricky, might need full rerun)
        # st.session_state[key] = not new_value # Attempt to revert


# --- Streamlit App Layout ---

st.set_page_config(layout="wide", page_title="WG Zimmer Watcher")

# Initialize session state
if "fetching" not in st.session_state:
    st.session_state.fetching = False
if "logs" not in st.session_state:
    st.session_state.logs = ["App loaded. Ready to fetch."]
if "notifications" not in st.session_state:
    st.session_state.notifications = []
if "all_listings" not in st.session_state:  # Store all listings loaded from DB
    st.session_state.all_listings = []
if "listings_dirty" not in st.session_state:  # Flag to reload listings from DB
    st.session_state.listings_dirty = True
if "fetch_error" not in st.session_state:
    st.session_state.fetch_error = None

# Check the queue for updates from the fetch thread
while not LOG_QUEUE.empty():
    msg_type, msg_payload = LOG_QUEUE.get()
    if msg_type == "log":
        st.session_state.logs.append(msg_payload)
    elif msg_type == "status":
        if msg_payload == "finished" or msg_payload == "error":
            st.session_state.fetching = False  # Re-enable button
        # Potentially add status messages to notifications
        # st.session_state.notifications.append(("info", f"Fetch status: {msg_payload}"))
    elif msg_type == "error":
        st.session_state.fetch_error = msg_payload  # Store last error
        st.session_state.notifications.append(("error", msg_payload))
    # Trigger a rerun to show log updates? Can cause flickering.
    # Consider batching updates or updating less frequently.
    st.rerun()  # Rerun to display new logs/status changes

# --- Sidebar ---
with st.sidebar:
    st.title("WG Zimmer Watcher")

    fetch_button_text = (
        "Fetching..." if st.session_state.fetching else "Fetch New Listings"
    )
    st.button(
        fetch_button_text,
        on_click=start_fetch,
        disabled=st.session_state.fetching,
        use_container_width=True,
    )

    if st.session_state.fetching:
        st.spinner("Fetching in progress...")

    st.markdown("---")
    st.subheader("Filters")

    # Filter: Frei ab Datum
    today = datetime.now().date()
    default_start = today + timedelta(days=60)  # Default start ~2 months from now
    default_end = today + timedelta(days=150)  # Default end ~5 months from now

    if "filter_frei_ab_start" not in st.session_state:
        st.session_state.filter_frei_ab_start = default_start
    if "filter_frei_ab_end" not in st.session_state:
        st.session_state.filter_frei_ab_end = default_end

    st.session_state.filter_frei_ab_start = st.date_input(
        "Verfügbar ab (Start)", value=st.session_state.filter_frei_ab_start
    )
    st.session_state.filter_frei_ab_end = st.date_input(
        "Verfügbar ab (Ende)", value=st.session_state.filter_frei_ab_end
    )

    # Filter: Miete
    if "filter_miete_min" not in st.session_state:
        st.session_state.filter_miete_min = 0
    if "filter_miete_max" not in st.session_state:
        st.session_state.filter_miete_max = 3000  # Set a reasonable default max

    min_miete, max_miete = st.slider(
        "Miete Range (CHF)",
        min_value=0,
        max_value=5000,  # Adjust max as needed
        value=(st.session_state.filter_miete_min, st.session_state.filter_miete_max),
        step=50,
    )
    st.session_state.filter_miete_min = min_miete
    st.session_state.filter_miete_max = max_miete

    # Filter: Status (Gemerkt / Aktiv / Gelöscht)
    status_options = ["Active", "Merkliste", "Deleted"]
    if "filter_status" not in st.session_state:
        st.session_state.filter_status = "Active"  # Default view
    st.session_state.filter_status = st.radio(
        "Anzeigen:",
        status_options,
        index=status_options.index(st.session_state.filter_status),
        horizontal=True,
    )

    # Force listing reload if filters changed or dirty flag set
    if (
        st.session_state.listings_dirty
        or "filter_frei_ab_start" not in st.session_state
    ):  # Initial load check
        st.session_state.all_listings = database.get_all_listings_stored(
            include_deleted=True
        )
        st.session_state.listings_dirty = False  # Reset flag


# --- Main Area ---

# Display Notifications
st.subheader("Status & Notifications")
if st.session_state.fetch_error:
    st.error(st.session_state.fetch_error)  # Show last error prominently

for n_type, n_msg in st.session_state.notifications:
    if n_type == "success":
        st.success(n_msg, icon="✅")
    elif n_type == "info":
        st.info(n_msg, icon="ℹ️")
    elif n_type == "warning":
        st.warning(n_msg, icon="⚠️")
    elif n_type == "error":
        st.error(n_msg, icon="❌")

# Log Output Area
with st.expander("Show Fetch Logs", expanded=False):
    st.text_area(
        "Logs",
        value="\n".join(st.session_state.logs),
        height=300,
        key="log_area",
        disabled=True,
    )

# Filter Listings for Display
st.subheader("Listings")
filtered_listings = st.session_state.all_listings

# Apply Status Filter
if st.session_state.filter_status == "Active":
    filtered_listings = [l for l in filtered_listings if l.status == "active"]
elif st.session_state.filter_status == "Merkliste":
    filtered_listings = [
        l for l in filtered_listings if l.gemerkt and l.status == "active"
    ]
elif st.session_state.filter_status == "Deleted":
    filtered_listings = [l for l in filtered_listings if l.status == "deleted"]

# Apply Date Filter (only if dates are valid)
if st.session_state.filter_frei_ab_start and st.session_state.filter_frei_ab_end:
    if st.session_state.filter_frei_ab_start > st.session_state.filter_frei_ab_end:
        st.warning("Start date for 'Frei ab' cannot be after end date.")
    else:
        start_dt = datetime.combine(
            st.session_state.filter_frei_ab_start, datetime.min.time()
        )
        end_dt = datetime.combine(
            st.session_state.filter_frei_ab_end, datetime.max.time()
        )
        filtered_listings = [
            l
            for l in filtered_listings
            if l.datum_ab_frei and start_dt <= l.datum_ab_frei <= end_dt
        ]

# Apply Miete Filter
filtered_listings = [
    l
    for l in filtered_listings
    if l.miete is not None
    and st.session_state.filter_miete_min
    <= l.miete
    <= st.session_state.filter_miete_max
]


# Display Listings
st.write(f"Displaying {len(filtered_listings)} listings.")

if not filtered_listings:
    st.info("No listings match the current filters.")
else:
    # Sort listings (e.g., by 'frei ab' date, descending)
    filtered_listings.sort(
        key=lambda l: l.datum_ab_frei if l.datum_ab_frei else datetime.min,
        reverse=False,
    )

    # Use columns for better layout potentially
    col1, col2 = st.columns(2)
    cols = [col1, col2]

    for i, listing in enumerate(filtered_listings):
        with cols[i % 2]:  # Alternate columns
            with st.container(border=True):
                if listing.status == "deleted":
                    st.markdown(f"~~*Listing Offline*~~")

                # Display Image if available
                if listing.img_url:
                    st.image(str(listing.img_url), width=200)  # Adjust width as needed

                # Main Info (handle potential None values)
                miete_str = (
                    f"{listing.miete:.2f} CHF" if listing.miete is not None else "N/A"
                )
                adresse_str = listing.adresse if listing.adresse else "N/A"
                frei_ab_str = (
                    listing.datum_ab_frei.strftime("%d.%m.%Y")
                    if listing.datum_ab_frei
                    else "N/A"
                )
                aufgegeben_str = (
                    listing.aufgegeben_datum.strftime("%d.%m.%Y")
                    if listing.aufgegeben_datum
                    else "N/A"
                )

                info_text = f"**{miete_str}** | {adresse_str}"
                if listing.status == "deleted":
                    st.markdown(f"~~{info_text}~~")
                else:
                    st.markdown(info_text)

                st.caption(f"Frei ab: {frei_ab_str} | Aufgegeben: {aufgegeben_str}")

                # Link and Actions
                subcol1, subcol2, subcol3 = st.columns([2, 1, 1])
                with subcol1:
                    st.link_button(
                        "Öffnen",
                        str(listing.url),
                        disabled=(listing.status == "deleted"),
                    )
                with subcol2:
                    st.checkbox(
                        "👁️",
                        key=f"gesehen_{listing.id}",
                        value=listing.gesehen,
                        on_change=update_db_status_callback,
                        args=(listing.id, "gesehen"),
                        help="Gesehen",
                        disabled=(listing.status == "deleted"),
                    )
                with subcol3:
                    st.checkbox(
                        "⭐",
                        key=f"gemerkt_{listing.id}",
                        value=listing.gemerkt,
                        on_change=update_db_status_callback,
                        args=(listing.id, "gemerkt"),
                        help="Merken",
                        disabled=(listing.status == "deleted"),
                    )
