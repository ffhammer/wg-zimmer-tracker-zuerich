from datetime import datetime

import streamlit as st

from src.models import BaseListing
from src.render.utils import handle_status_update, select_listing


def render_page_lists(filtered_listings: list[BaseListing]):
    for listing in filtered_listings:
        with st.container():
            col1, col2 = st.columns([1, 3])  # Adjust column ratio as needed

            with col1:
                if listing.img_urls:
                    st.image(str(listing.img_urls[0]), width=150)

            with col2:
                detail_col1, detail_col2, detail_col3 = st.columns(3)
                with detail_col1:
                    st.markdown(f"**Website:** {listing.website or 'N/A'}")
                with detail_col2:
                    st.markdown(
                        f"**Adresse:** {listing.straße_und_hausnummer or 'N/A'}"
                    )
                miete_str = (
                    f"{listing.miete:.2f} CHF" if listing.miete is not None else "N/A"
                )
                with detail_col3:
                    st.markdown(f"**Miete:** {miete_str}")
                frei_ab_str = (
                    listing.datum_ab_frei.strftime("%d.%m.%Y")
                    if listing.datum_ab_frei
                    else "N/A"
                )

                if listing.datum_frei_bis and isinstance(
                    listing.datum_frei_bis, datetime
                ):
                    frei_bis_str = listing.datum_frei_bis.strftime("%d.%m.%Y")
                elif listing.datum_frei_bis and isinstance(listing.datum_frei_bis, str):
                    frei_bis_str = listing.datum_frei_bis
                else:
                    frei_bis_str = "N/A"

                aufgegeben_str = (
                    listing.aufgegeben_datum.strftime("%d.%m.%Y")
                    if listing.aufgegeben_datum
                    else "N/A"
                )

                detail_col1, detail_col2, detail_col3 = st.columns(3)
                with detail_col1:
                    st.markdown(f"**Frei ab:** {frei_ab_str}")
                with detail_col2:
                    st.markdown(f"**Frei bis:** {frei_bis_str}")
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
