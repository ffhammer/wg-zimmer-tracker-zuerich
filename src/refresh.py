import os
from datetime import datetime

import pytz
from loguru import logger

from src import students_ch, wg_zimmer_ch, woko
from src.database import update_database
from src.models import DataBaseUpdate, Webiste

TIME_ZONE = pytz.timezone(os.environ["TIME_ZONE"])


def refresh_all() -> dict[Webiste, DataBaseUpdate]:
    logger.info("Starting to refresh all")

    now = datetime.now()
    statuses: dict[Webiste, DataBaseUpdate] = {}

    urls = wg_zimmer_ch.fetch_table()
    if urls:
        statuses[Webiste.wg_zimmer_ch] = update_database(
            urls, now, Webiste.wg_zimmer_ch
        )

    # students_ch
    urls = students_ch.fetch_table()
    statuses[Webiste.students_ch] = update_database(urls, now, Webiste.students_ch)

    # woko
    urls = woko.fetch_table()
    statuses[Webiste.woko] = update_database(urls, now, Webiste.woko)

    # wg_zimmer_ch

    return statuses
