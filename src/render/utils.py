import streamlit as st

from src.database import (
    update_listing_user_status,
)


def handle_status_update(url: str, field: str, value: bool):
    """Callback function to update status and rerun."""
    update_listing_user_status(url=url, field=field, value=value)


def select_listing(listing_id):
    st.session_state.selected_id = listing_id
