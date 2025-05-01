# src/app.py
from datetime import date, datetime, time
from typing import List, Optional

import streamlit as st

from src.database import (
    get_all_listings_stored,
    get_last_update,
)
from src.models import DataBaseUpdate, WGZimmerCHListing
from src.render.big_map import render_map
from src.render.detail_page import render_detail_page
from src.render.page_lists import render_page_lists
from src.wg_zimmer_ch import start_fetch_table_terminal_process

st.set_page_config(layout="wide", page_title="WG Zimmer Tracker")

# Session state to track “which listing” is in detail mode
if "selected_id" not in st.session_state:
    st.session_state.selected_id = None


# --- Helper Functions ---


# Function to handle the status update and force a re-run


# --- Load Data ---
# Load data fresh each time to reflect updates from callbacks or DB checks
# Caching might be complex here due to external DB file and status updates
all_listings: List[WGZimmerCHListing] = get_all_listings_stored(include_deleted=False)
last_db_update_info: Optional[DataBaseUpdate] = None

# --- Sidebar ---
st.sidebar.title("WG Zimmer Tracker")
st.sidebar.markdown("---")

# 1. Fetch & Update Controls
st.sidebar.header("Daten Aktualisieren")
if st.sidebar.button("Neuen Fetch starten (öffnet Terminal)"):
    try:
        start_fetch_table_terminal_process()
        st.sidebar.success("Fetch-Prozess im Terminal gestartet.")
        st.sidebar.info(
            "Bitte warte bis der Fetch abgeschlossen ist und klicke dann auf 'Neue Daten prüfen & DB aktualisieren'."
        )
    except Exception as e:
        st.sidebar.error(f"Fehler beim Starten des Fetch-Prozesses: {e}")

update_results = None
if st.sidebar.button("Neue Daten prüfen & DB aktualisieren"):
    with st.spinner("Prüfe auf neue Daten und aktualisiere Datenbank..."):
        try:
            # update_results = check_for_new_data_and_update()
            # Refresh data after update
            all_listings = get_all_listings_stored(include_deleted=False)
            last_db_update_info = get_last_update("students.ch")
            st.sidebar.success("Datenbank erfolgreich geprüft/aktualisiert!")
            st.rerun()  # Rerun to apply potential new data and update display
        except Exception as e:
            st.sidebar.error(f"Fehler beim Datenbank-Update: {e}")

st.sidebar.markdown("---")

# Display Last Update Info
st.sidebar.header("Letztes DB Update")
if last_db_update_info:
    st.sidebar.metric(
        "Datum",
        (
            last_db_update_info.date.strftime("%Y-%m-%d %H:%M:%S")
            if last_db_update_info.date
            else "N/A"
        ),
    )
    col1, col2, col3 = st.columns(3)
    col1.metric("Neu", last_db_update_info.n_new)
    col2.metric("Aktualisiert", last_db_update_info.n_updated)
    col3.metric("Gelöscht", last_db_update_info.n_deleted)
else:
    st.sidebar.info("Noch keine Update-Informationen vorhanden.")

st.sidebar.markdown("---")

# 2. Filter Controls
st.sidebar.header("Filter")

# Date Filter (Default: September/October of current year)
current_year = datetime.now().year
default_start_date = date(current_year, 9, 1)
default_end_date = date(current_year, 10, 31)

date_range = st.sidebar.date_input(
    "Frei ab Datum (Bereich)",
    value=(default_start_date, default_end_date),
    min_value=date(current_year - 1, 1, 1),
    max_value=date(current_year + 2, 12, 31),
)
start_date_dt = (
    datetime.combine(date_range[0], time.min) if len(date_range) > 0 else None
)
end_date_dt = datetime.combine(date_range[1], time.max) if len(date_range) > 1 else None


# Price Filter
min_db_price = min(
    [listing.miete for listing in all_listings if listing.miete is not None] or [0]
)  # Handle empty or all None
max_db_price = max(
    [listing.miete for listing in all_listings if listing.miete is not None] or [1000]
)  # Handle empty or all None
# Ensure max_db_price is at least a bit higher than min_db_price for the slider
max_slider_limit = max(max_db_price, min_db_price + 100, 1000)

price_range = st.sidebar.slider(
    "Mietpreis (CHF)",
    min_value=0,
    max_value=int(max_slider_limit + 100),  # Add some buffer
    value=(
        0,
        int(max_db_price if max_db_price > 0 else 1000),
    ),  # Default: 0 to max found or 1000
    step=50,
)
min_price, max_price = price_range

# User Status Filter
filter_not_seen = st.sidebar.checkbox("Nur nicht gesehene anzeigen", value=False)
filter_not_bookmarked = st.sidebar.checkbox("Nur nicht gemerkte anzeigen", value=False)
filter_only_bookmarked = st.sidebar.checkbox("Nur gemerkte anzeigen", value=False)

st.sidebar.markdown("---")

# 3. Sorting Controls
st.sidebar.header("Sortierung")
sort_option = st.sidebar.selectbox(
    "Sortieren nach",
    [
        "Datum Frei ab (absteigend)",
        "Datum Frei ab (aufsteigend)",
        "Preis (aufsteigend)",
        "Preis (absteigend)",
        "Datum Aufgegeben (neueste zuerst)",
        "Datum Aufgegeben (älteste zuerst)",
    ],
)


# --- Main Area ---
st.title("Verfügbare WG Zimmer")


# If a listing is selected, show detail view and bail out

if st.session_state.selected_id:
    # grab the one listing
    render_detail_page(all_listings=all_listings)

    st.stop()

# Apply Filters
filtered_listings = all_listings

# Date Filter
if start_date_dt and end_date_dt:
    filtered_listings = [
        listing
        for listing in filtered_listings
        if listing.datum_ab_frei
        and start_date_dt <= listing.datum_ab_frei <= end_date_dt
    ]

# Price Filter
filtered_listings = [
    listing
    for listing in filtered_listings
    if listing.miete is not None and min_price <= listing.miete <= max_price
]

# User Status Filters
if filter_not_seen:
    filtered_listings = [
        listing for listing in filtered_listings if not listing.gesehen
    ]
if filter_not_bookmarked:
    # This overrides the "only bookmarked" if both are checked
    filtered_listings = [
        listing for listing in filtered_listings if not listing.gemerkt
    ]
elif filter_only_bookmarked:
    # Only apply if "not bookmarked" isn't checked
    filtered_listings = [listing for listing in filtered_listings if listing.gemerkt]


# Apply Sorting
def sort_key_price(listing: WGZimmerCHListing):
    return (
        listing.miete if listing.miete is not None else float("inf")
    )  # None treated as high price


def sort_key_date_frei(listing: WGZimmerCHListing):
    # Treat None date as very far in the future for ascending sort
    return listing.datum_ab_frei if listing.datum_ab_frei is not None else datetime.max


def sort_key_date_aufgegeben(listing: WGZimmerCHListing):
    # Treat None date as very old for newest-first sort (descending)
    return (
        listing.aufgegeben_datum
        if listing.aufgegeben_datum is not None
        else datetime.min
    )


if sort_option == "Preis (aufsteigend)":
    filtered_listings.sort(key=sort_key_price)
elif sort_option == "Preis (absteigend)":
    filtered_listings.sort(key=sort_key_price, reverse=True)
elif sort_option == "Datum Frei ab (aufsteigend)":
    filtered_listings.sort(key=sort_key_date_frei)
elif sort_option == "Datum Frei ab (absteigend)":
    filtered_listings.sort(key=sort_key_date_frei, reverse=True)
elif sort_option == "Datum Aufgegeben (neueste zuerst)":
    filtered_listings.sort(key=sort_key_date_aufgegeben, reverse=True)
elif sort_option == "Datum Aufgegeben (älteste zuerst)":
    filtered_listings.sort(key=sort_key_date_aufgegeben)

# --- Map Widget ---
render_map(filtered_listings)

# Display Results
st.subheader(f"{len(filtered_listings)} von {len(all_listings)} Listings angezeigt")

if update_results:
    st.success(
        f"Update abgeschlossen: {len(update_results)} neue Datei(en) verarbeitet."
    )
    for res in update_results:
        st.info(
            f"- {res.date.strftime('%Y-%m-%d %H:%M')}: {res.n_new} neu, {res.n_updated} aktualisiert, {res.n_deleted} gelöscht."
        )
    st.markdown("---")  # Add separator after update message


if not filtered_listings:
    st.warning("Keine Listings entsprechen den aktuellen Filterkriterien.")
else:
    # Display listings
    render_page_lists(filtered_listings)
