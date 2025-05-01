import json
from datetime import datetime
from pathlib import Path

from src import students_ch, woko
from src.database import get_last_update, update_database
from src.models import DataBaseUpdate, Webiste


def refresh_all() -> dict[Webiste, DataBaseUpdate]:
    now = datetime.now()
    statuses: dict[Webiste, DataBaseUpdate] = {}

    # students_ch
    urls = students_ch.fetch_table()
    statuses[Webiste.students_ch] = update_database(urls, now, Webiste.students_ch)

    # woko
    urls = woko.fetch_table()
    statuses[Webiste.woko] = update_database(urls, now, Webiste.woko)

    # wg_zimmer_ch
    latest = max(
        (p for p in Path("wg-zimmer-listings").glob("*.json")),
        key=lambda p: p.stem,
    )
    last = get_last_update(Webiste.wg_zimmer_ch)
    if not last or datetime.fromisoformat(latest.stem) > last.date:
        urls = list(set(json.load(open(latest))))

        statuses[Webiste.wg_zimmer_ch] = update_database(
            urls, now, Webiste.wg_zimmer_ch
        )

    return statuses
