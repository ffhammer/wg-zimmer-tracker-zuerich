import pandas as pd
import pydeck as pdk
import streamlit as st

from src.models import BaseListing


def render_map(filtered_listings: list[BaseListing]):
    map_df = pd.DataFrame(
        [
            {
                "lat": listing.latitude,
                "lon": listing.longitude,
                "url": str(listing.url),
                "adresse": listing.straße_und_hausnummer or "",
                "preis": listing.miete,
            }
            for listing in filtered_listings
            if listing.latitude is not None and listing.longitude is not None
        ]
    )
    if map_df.empty:
        return
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
