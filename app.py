# src/app.py
from datetime import date, datetime, time
from typing import Optional

import streamlit as st

from src.database import (
    get_all_listings_stored,
    get_last_update,
)
from src.models import BaseListing, DataBaseUpdate, Webiste
from src.refresh import refresh_all
from src.render.big_map import render_map
from src.render.detail_page import render_detail_page
from src.render.page_lists import render_page_lists

st.set_page_config(layout="wide", page_title="WG Zimmer Tracker")

# Session state to track “which listing” is in detail mode
if "selected_id" not in st.session_state:
    st.session_state.selected_id = None


# --- Load Data ---
# Load data fresh each time to reflect updates from callbacks or DB checks
# Caching might be complex here due to external DB file and status updates
all_listings = get_all_listings_stored(include_deleted=False)
last_db_update_info: Optional[DataBaseUpdate] = {i: get_last_update(i) for i in Webiste}

# --- Sidebar ---
st.sidebar.title("WG Zimmer Tracker")
st.sidebar.markdown("---")

# 1. Fetch & Update Controls
st.sidebar.header("Daten Aktualisieren")

if st.sidebar.button("Neue Daten fetchen & DB aktualisieren"):
    with st.spinner("Prüfe auf neue Daten und aktualisiere Datenbank..."):
        try:
            statuses = refresh_all()
            st.sidebar.success("Datenbank erfolgreich geprüft/aktualisiert!")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Fehler beim Datenbank-Update: {e}")


st.sidebar.markdown("---")

# 2. Filter Controls
st.sidebar.header("Filter")

# Date Filter (Default: September/October of current year)
current_year = datetime.now().year
default_start_date = date(current_year, 8, 1)
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
    [listing.miete for listing in all_listings if listing.miete is not None] or [1500]
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

selected_websites = st.sidebar.multiselect(
    "Websites filtern",
    options=[w.value for w in Webiste],
    default=[w.value for w in Webiste],
)

max_bike_min = st.sidebar.slider("Max. Fahrrad-Minuten", 0, 60, 60)


# User Status Filter
filter_not_seen = st.sidebar.checkbox("Nur nicht gesehene anzeigen", value=False)
filter_not_bookmarked = st.sidebar.checkbox(
    "Nur nicht kontaktiert anzeigen", value=True
)
filter_only_bookmarked = st.sidebar.checkbox("Nur kontaktiert anzeigen", value=False)

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
# If a listing is selected, show detail view and bail out

if st.session_state.selected_id:
    # grab the one listing
    render_detail_page(all_listings=all_listings)

    st.stop()

# Display Last Update Info
st.header("Letztes DB Update")
if len(last_db_update_info):
    for col, (w, info) in zip(
        st.columns(len(last_db_update_info)), last_db_update_info.items()
    ):
        with col:
            st.subheader(w.value)
            if info:
                st.metric("Datum", info.date.strftime("%Y-%m-%d %H:%M:%S"))
                col1, col2, col3 = st.columns(3)
                col1.metric("Neu", info.n_new)
                col2.metric("Aktualisiert", info.n_updated)
                col3.metric("Gelöscht", info.n_deleted)
            else:
                st.info("Kein Update vorhanden")
else:
    st.info("Noch keine Update-Informationen vorhanden.")
st.markdown("---")


st.title("Verfügbare WG Zimmer")


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
filtered_listings = [
    listing
    for listing in filtered_listings
    if listing.website.value in selected_websites
]

filtered_listings = [
    listing
    for listing in filtered_listings
    if not listing.bike or listing.bike.duration_min <= max_bike_min
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
def sort_key_price(listing: BaseListing):
    return (
        listing.miete if listing.miete is not None else float("inf")
    )  # None treated as high price


def sort_key_date_frei(listing: BaseListing):
    # Treat None date as very far in the future for ascending sort
    return listing.datum_ab_frei if listing.datum_ab_frei is not None else datetime.max


def sort_key_date_aufgegeben(listing: BaseListing):
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


# split new vs existing
new_listings = []

new_listings = [
    listing
    for listing in filtered_listings
    if (info := last_db_update_info.get(listing.website))
    and listing.first_seen.date() == info.date.date()
]
other_listings = [
    listing for listing in filtered_listings if listing not in new_listings
]

if new_listings:
    st.subheader("Neue Listings")
    render_page_lists(new_listings)

if other_listings:
    st.subheader("Weitere Listings")
    render_page_lists(other_listings)
