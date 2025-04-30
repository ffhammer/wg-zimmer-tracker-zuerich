from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from src.fetch_listing_lists.ListingScraped import ListingScraped


class DataBaseUpdate(BaseModel):
    n_new: int
    n_deleted: int
    n_updated: int
    date: datetime


class Journey(BaseModel):
    type: Literal["walk", "wait", "B", "T", "S", "IR", "IC", "EC"]
    length_min: int
    latitude: Optional[float]
    longitude: Optional[float]

    @property
    def emoji(self) -> str:
        emoji_map = {
            "walk": "🚶",
            "wait": "⏳",
            "B": "🚌",  # Bus
            "T": "🚋",  # Tram
            "S": "🚆",  # S-Bahn / Suburban train
            "IR": "🚄",  # InterRegio
            "IC": "🚅",  # InterCity
            "EC": "🚅",  # EuroCity
        }
        return emoji_map.get(self.type, "❓")

    def __repr__(self) -> str:
        return f"{self.emoji} – {self.length_min} min"


class PublicTransportConnection(BaseModel):
    total_time_min: int
    journeys: List[Journey]

    def __repr__(self) -> str:
        lines = [f"Total: {self.total_time_min} min"]
        lines += [repr(j) for j in self.journeys]
        return "\n".join(lines)


class Waypoint(BaseModel):
    latitude: float
    longitude: float


class BikeConnection(BaseModel):
    duration_min: float
    dist_km: float

    waypoints: list[Waypoint]

    def __repr__(self) -> str:
        return f"🚴 Bike: {self.dist_km:.1f} km in {self.duration_min:.0f} min"


class ListingStored(ListingScraped):
    gesehen: bool = Field(default=False, description="Vom User als gesehen markiert")
    gemerkt: bool = Field(default=False, description="Vom User gemerkt")
    status: Literal["active", "deleted"] = Field(
        default="active", description="Ist das Listing noch aktuell?"
    )
    first_seen: datetime = Field(
        default_factory=datetime.now,
        description="Wann wurde das Listing zum ersten Mal gesehen?",
    )
    last_seen: datetime = Field(
        default_factory=datetime.now,
        description="Wann wurde das Listing zuletzt im Fetch gesehen?",
    )

    region: Optional[str] = None
    adresse: Optional[str] = None
    ort: Optional[str] = None
    beschreibung: Optional[str] = None
    wir_suchen: Optional[str] = None
    wir_sind: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    img_urls: list = Field([])

    public_transport: Optional[PublicTransportConnection] = None
    bike: Optional[BikeConnection] = None

    # Eindeutige ID für Streamlit-Keys etc. (kann einfach die URL sein)
    @property
    def id(self) -> str:
        return str(self.url)

    # Hilfsmethode zum Aktualisieren aus einem neuen Scrape
    def update_from_scraped(self, scraped: "ListingScraped", dt: datetime):
        # Update fields that might change (though unlikely for WGZimmer)
        self.miete = scraped.miete
        self.adresse = scraped.adresse
        self.img_url = scraped.img_url
        self.aufgegeben_datum = scraped.aufgegeben_datum
        self.datum_ab_frei = scraped.datum_ab_frei
        # Update internal status
        self.last_seen = dt
        self.status = "active"  # Mark as active again if it was deleted
