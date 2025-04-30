# WGZimmer.ch Tracker

Automated tracker for wgzimmer.ch listings using browser automation (Gemini LLM) and a Streamlit UI.

## Features

- Fetches listings based on price/region.
- Stores listings in a local TinyDB (`db.json`).
- Streamlit UI to view, filter (price, date, seen/bookmarked), sort, and manage listings.
- Mark listings as 'seen' or 'bookmarked'.
- Trigger new fetches and database updates from the UI.
