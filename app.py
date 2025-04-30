# src/app.py
import streamlit as st
from datetime import datetime, date, time
from typing import List, Optional
import logging
import pandas as pd
import pydeck as pdk

from src.database import (
    get_all_listings_stored,
    update_listing_user_status,
    check_for_new_data_and_update,
    get_last_update,
)
from src.models import ListingStored, DataBaseUpdate
from src.fetch_listing_lists.start_job import start_terminal_process

st.set_page_config(layout="wide", page_title="WG Zimmer Tracker")

# Session state to track “which listing” is in detail mode
if "selected_id" not in st.session_state:
    st.session_state.selected_id = None

logging.basicConfig()
logging.getLogger("wg-zimmer.zc-fetch").setLevel(logging.DEBUG)

# --- Helper Functions ---


# Function to handle the status update and force a re-run
def handle_status_update(url: str, field: str, value: bool):
    """Callback function to update status and rerun."""
    update_listing_user_status(url=url, field=field, value=value)


def select_listing(listing_id):
    st.session_state.selected_id = listing_id
    st.rerun()


# --- Load Data ---
# Load data fresh each time to reflect updates from callbacks or DB checks
# Caching might be complex here due to external DB file and status updates
all_listings: List[ListingStored] = get_all_listings_stored(include_deleted=False)
last_db_update_info: Optional[DataBaseUpdate] = get_last_update()

# --- Sidebar ---
st.sidebar.title("WG Zimmer Tracker")
st.sidebar.markdown("---")

# 1. Fetch & Update Controls
st.sidebar.header("Daten Aktualisieren")
if st.sidebar.button("Neuen Fetch starten (öffnet Terminal)"):
    try:
        # NOTE: start_terminal_process in your provided code doesn't actually use the
        # export_filename argument, as fetch_new_user.py creates its own timestamped file.
        # We call it without the filename argument.
        start_terminal_process()
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
            update_results = check_for_new_data_and_update()
            # Refresh data after update
            all_listings = get_all_listings_stored(include_deleted=False)
            last_db_update_info = get_last_update()
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
    [l.miete for l in all_listings if l.miete is not None] or [0]
)  # Handle empty or all None
max_db_price = max(
    [l.miete for l in all_listings if l.miete is not None] or [1000]
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
        "Datum Frei ab (aufsteigend)",
        "Datum Frei ab (absteigend)",
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
    detail = next(
        (l for l in all_listings if l.id == st.session_state.selected_id),
        None,
    )
    if detail:
        st.button(
            "← Zurück zur Liste",
            on_click=lambda: st.session_state.update(selected_id=None),
        )
        st.header("Detailansicht")
        st.markdown(f"**Region:** {detail.region or '–'}")
        st.markdown(f"**Adresse:** {detail.adresse or '–'}")
        st.markdown(f"**Ort:** {detail.ort or '–'}")
        st.markdown("**Beschreibung:**")
        st.markdown(f"{detail.beschreibung or '–'}")
        st.markdown("**Wir suchen:**")
        st.markdown(f"{detail.wir_suchen or '–'}")
        st.markdown("**Wir sind:**")
        st.markdown(f"{detail.wir_sind or '–'}")
        # status flags

        if detail.img_urls:
            cols = st.columns(3)
            for i, url in enumerate(detail.img_urls):
                with cols[i % 3]:
                    st.image(url, use_container_width=True)

        one, two, three = st.columns(3)
        with one:
            st.checkbox(
                "Gesehen",
                value=detail.gesehen,
                key=f"gesehen_{detail.id}",  # Unique key is crucial
                on_change=handle_status_update,
                args=(
                    detail.id,
                    "gesehen",
                    not detail.gesehen,
                ),  # Pass current url, field, and *new* value
            )
        with two:

            st.checkbox(
                "Gemerkt",
                value=detail.gemerkt,
                key=f"gemerkt_{detail.id}",  # Unique key
                on_change=handle_status_update,
                args=(
                    detail.id,
                    "gemerkt",
                    not detail.gemerkt,
                ),  # Pass current url, field, and *new* value
            )

        with three:
            if detail.url:
                st.link_button("Öffnen auf wgzimmer.ch", url=str(detail.url))

        # map at bottom
        if detail.latitude and detail.longitude:

            df = pd.DataFrame([{"lat": detail.latitude, "lon": detail.longitude}])
            layer = pdk.Layer(
                "ScatterplotLayer",
                data=df,
                get_position=["lon", "lat"],
                get_radius=50,
                get_fill_color=[255, 0, 0, 200],
                pickable=True,
                auto_highlight=True,
            )
            view = pdk.ViewState(
                latitude=detail.latitude, longitude=detail.longitude, zoom=13
            )
            st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view))
    else:
        st.error("Listing nicht gefunden.")
    st.stop()

# Apply Filters
filtered_listings = all_listings

# Date Filter
if start_date_dt and end_date_dt:
    filtered_listings = [
        l
        for l in filtered_listings
        if l.datum_ab_frei and start_date_dt <= l.datum_ab_frei <= end_date_dt
    ]

# Price Filter
filtered_listings = [
    l
    for l in filtered_listings
    if l.miete is not None and min_price <= l.miete <= max_price
]

# User Status Filters
if filter_not_seen:
    filtered_listings = [l for l in filtered_listings if not l.gesehen]
if filter_not_bookmarked:
    # This overrides the "only bookmarked" if both are checked
    filtered_listings = [l for l in filtered_listings if not l.gemerkt]
elif filter_only_bookmarked:
    # Only apply if "not bookmarked" isn't checked
    filtered_listings = [l for l in filtered_listings if l.gemerkt]


# Apply Sorting
def sort_key_price(listing: ListingStored):
    return (
        listing.miete if listing.miete is not None else float("inf")
    )  # None treated as high price


def sort_key_date_frei(listing: ListingStored):
    # Treat None date as very far in the future for ascending sort
    return listing.datum_ab_frei if listing.datum_ab_frei is not None else datetime.max


def sort_key_date_aufgegeben(listing: ListingStored):
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
map_df = pd.DataFrame(
    [
        {
            "lat": l.latitude,
            "lon": l.longitude,
            "url": str(l.url),
            "adresse": l.adresse or "",
            "preis": l.miete,
        }
        for l in filtered_listings
        if l.latitude is not None and l.longitude is not None
    ]
)

if not map_df.empty:
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_df,
        get_position=["lon", "lat"],
        get_radius=50,
        get_fill_color=[255, 0, 0, 200],
        pickable=True,
        auto_highlight=True,
    )
    tooltip = {
        "html": "<b>{adresse}</b><br/><b>{preis}</b>",
        "style": {"backgroundColor": "rgba(0, 0, 0, 0.8)", "color": "white"},
    }
    view_state = pdk.ViewState(
        latitude=map_df["lat"].mean(),
        longitude=map_df["lon"].mean(),
        zoom=11,
    )
    st.pydeck_chart(
        pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip)
    )

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
    for listing in filtered_listings:
        with st.container():
            col1, col2 = st.columns([1, 3])  # Adjust column ratio as needed

            with col1:
                if listing.img_url:
                    st.image(str(listing.img_url), width=150)
                else:
                    st.image(
                        "https://via.placeholder.com/150x100.png?text=No+Image",
                        width=150,
                    )  # Placeholder

            with col2:
                st.markdown(f"**Adresse:** {listing.adresse or 'N/A'}")
                miete_str = (
                    f"{listing.miete:.2f} CHF" if listing.miete is not None else "N/A"
                )
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

                detail_col1, detail_col2, detail_col3, detail_col_4 = st.columns(4)
                with detail_col1:
                    st.markdown(f"**Miete:** {miete_str}")
                with detail_col2:
                    st.markdown(f"**Frei ab:** {frei_ab_str}")
                with detail_col3:
                    st.markdown(f"**Aufgegeben am:** {aufgegeben_str.strip()}")

                # Status Toggles (Checkboxes for direct interaction)
                action_col1, action_col2, action_col3 = st.columns(
                    [1, 1, 2]
                )  # Space out checkboxes
                with action_col1:
                    st.checkbox(
                        "Gesehen",
                        value=listing.gesehen,
                        key=f"gesehen_{listing.id}",  # Unique key is crucial
                        on_change=handle_status_update,
                        args=(
                            listing.id,
                            "gesehen",
                            not listing.gesehen,
                        ),  # Pass current url, field, and *new* value
                    )
                with action_col2:
                    st.checkbox(
                        "Gemerkt",
                        value=listing.gemerkt,
                        key=f"gemerkt_{listing.id}",  # Unique key
                        on_change=handle_status_update,
                        args=(
                            listing.id,
                            "gemerkt",
                            not listing.gemerkt,
                        ),  # Pass current url, field, and *new* value
                    )
                with action_col3:
                    st.button(
                        "Details",
                        key=f"detail_{listing.id}",
                        on_click=select_listing,
                        args=(listing.id,),
                    )
            st.divider()  # Separator between listings
