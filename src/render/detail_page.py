# src/app.py

import pandas as pd
import pydeck as pdk
import streamlit as st

from src.database import save_draft
from src.generate_draft import generate_draft, get_personal_information
from src.locations import ETH_LOCATION
from src.models import BaseListing, ExampleDraft
from src.render.utils import handle_status_update


def render_detail_map(detail: BaseListing) -> None:
    layers: list[pdk.Layer] = []

    # Listing location
    layers.append(
        pdk.Layer(
            "ScatterplotLayer",
            pd.DataFrame([{"lat": detail.latitude, "lon": detail.longitude}]),
            get_position=["lon", "lat"],
            get_radius=50,
            get_fill_color=[255, 0, 0, 200],
            pickable=True,
        )
    )

    # ETH location
    layers.append(
        pdk.Layer(
            "ScatterplotLayer",
            pd.DataFrame(
                [{"lat": ETH_LOCATION.latitutude, "lon": ETH_LOCATION.longitude}]
            ),
            get_position=["lon", "lat"],
            get_radius=50,
            get_fill_color=[0, 0, 255, 200],
            pickable=True,
        )
    )

    # Bike route
    if detail.bike and detail.bike.waypoints:
        bike_path = [[wp.longitude, wp.latitude] for wp in detail.bike.waypoints]
        layers.append(
            pdk.Layer(
                "PathLayer",
                pd.DataFrame([{"path": bike_path}]),
                get_path="path",
                get_width=4,
                get_color=[0, 255, 0],
            )
        )

    # Public transport route
    if detail.public_transport:
        pts = [
            (j.longitude, j.latitude)
            for j in detail.public_transport.journeys
            if j.longitude and j.latitude
        ]
        if len(pts) > 1:
            layers.append(
                pdk.Layer(
                    "PathLayer",
                    pd.DataFrame([{"path": pts}]),
                    get_path="path",
                    get_width=4,
                    get_color=[255, 165, 0],
                    dash_array=[10, 10],
                )
            )

    view = pdk.ViewState(latitude=detail.latitude, longitude=detail.longitude, zoom=13)
    st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view))


def render_detail_page(all_listings: list[BaseListing]) -> None:
    detail = next(
        (
            listing
            for listing in all_listings
            if listing.id == st.session_state.selected_id
        ),
        None,
    )
    if not detail:
        st.error("Listing nicht gefunden.")

    st.button(
        "← Zurück zur Liste",
        on_click=lambda: st.session_state.update(selected_id=None),
    )
    st.header("Detailansicht")
    st.markdown(f"**Website:** {detail.website}")
    st.markdown(f"**Adresse:** {detail.straße_und_hausnummer or '–'}")
    st.markdown(f"**Ort:** {detail.plz_und_stadt or '–'}")
    st.markdown("**Beschreibung:**")
    st.markdown(f"{detail.beschreibung or '–'}")

    for atr in detail.additional_fields:
        st.markdown(f"**{atr.replace('_', ' ').title()}:**")
        st.markdown(f"{getattr(detail, atr) or '–'}")
    # status flags

    if detail.img_urls:
        cols = st.columns(3)
        for i, url in enumerate(detail.img_urls):
            with cols[i % 3]:
                st.image(str(url), use_container_width=True)

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
            "Kontaktiert",
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
            st.link_button(f"Öffnen auf {detail.website}", url=str(detail.url))

    one, two = st.columns(2)
    with one:
        if detail.public_transport:
            st.markdown("**Öffis:**")
            st.markdown(
                f"""```
            {detail.public_transport.__repr__()}
            """,
                unsafe_allow_html=True,
            )
    with two:
        if detail.bike:
            st.markdown("**Fahrrad:**")
            st.markdown(detail.bike.__repr__())

    # map at bottom
    render_detail_map(detail=detail)

    st.markdown("---")
    st.markdown("## Draft Generation")

    placeholder = st.empty()
    if st.button("Generate Inital Draft"):
        content = ""
        for chunk in generate_draft(listing=detail):
            content += chunk
            placeholder.text_area("Draft", value=content, height=200)

    st.text_area(
        "Personal and Listing Information",
        value=f"Personal Information {get_personal_information()}\nListings information {detail.to_llm_input(include_images=False)}",
        height=500,
    )

    final_draft = st.text_area(
        "Final Draft",
        value="",
        height=500,
    )
    if st.button("Save Final Draft"):
        save_draft(ExampleDraft(listing_url=detail.url, content=final_draft))
