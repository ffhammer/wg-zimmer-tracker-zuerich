import json
from datetime import datetime
from enum import StrEnum
from typing import List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, HttpUrl


class Webiste(StrEnum):
    wg_zimmer_ch = "wg-zimmer.ch"
    woko = "woko.ch"
    students_ch = "students.ch"


class DataBaseUpdate(BaseModel):
    website: Webiste
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


class BaseListing(BaseModel):
    additional_fields: list[str]
    website: Webiste

    url: HttpUrl = Field(None, description="die url zu dem specifischen post")

    aufgegeben_datum: Optional[datetime] = Field(
        None, description="das datum wo das inserat aufgegeb wurde"
    )
    datum_ab_frei: Optional[datetime] = Field(
        None, description="das datum ab dem das inserat frei ist"
    )
    datum_frei_bis: Optional[datetime | str] = None
    miete: Optional[float] = Field(None, description="miete in schweizer franken")
    größe_in_m2: Optional[float] = None
    contact_mail: Optional[EmailStr] = None
    beschreibung: Optional[str] = None
    img_urls: list[HttpUrl] = Field([])

    # Ortungs spezifisch
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    straße_und_hausnummer: Optional[str] = None
    plz_und_stadt: Optional[str] = None
    region: Optional[str] = "Zürich (Stadt)"

    # hinweg
    public_transport: Optional[PublicTransportConnection] = None
    bike: Optional[BikeConnection] = None

    # specific for our application
    gesehen: bool = Field(default=False, description="Vom User als gesehen markiert")
    gemerkt: bool = Field(default=False, description="Vom User gemerkt")
    status: Literal["active", "deleted"] = Field(
        default="active", description="Ist das Listing noch aktuell?"
    )
    first_seen: datetime = Field(
        default_factory=datetime.now,
        description="Wann wurde das Listing zum ersten Mal gesehen? -> db intern",
    )
    last_seen: datetime = Field(
        default_factory=datetime.now,
        description="Wann wurde das Listing zuletzt im Fetch gesehen? -> db intern",
    )

    @property
    def id(self) -> str:
        return str(self.url)

    def update(self, dt: datetime) -> None:
        self.last_seen = dt
        self.status = "active"  # Mark as active again if it was deleted

    def dump_json_serializable(self, **kwargs):
        return json.loads(self.model_dump_json(**kwargs))


class StudentsCHListing(BaseListing):
    # empty child class
    additional_fields: list[str] = Field([])
    website: Webiste = Webiste.students_ch


class WokoListing(BaseListing):
    additional_fields: list[str] = Field([])
    website: Webiste = Webiste.woko


class WGZimmerCHListing(BaseListing):
    additional_fields: list[str] = Field(["wir_suchen", "wir_sind"])
    website: Webiste = Webiste.wg_zimmer_ch

    wir_suchen: Optional[str] = None
    wir_sind: Optional[str] = None


WEBSITE_TO_MODEL: dict[Webiste, BaseListing] = {
    Webiste.wg_zimmer_ch: WGZimmerCHListing,
    Webiste.woko: WokoListing,
    Webiste.students_ch: StudentsCHListing,
}
