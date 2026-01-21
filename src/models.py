import json
from datetime import datetime
from enum import StrEnum
from typing import List, Literal, Optional

import requests
from pydantic import BaseModel, EmailStr, Field, HttpUrl
from sqlmodel import Column, Enum, SQLModel
from sqlmodel import Field as SQLField

from src.logger import logger


class Webiste(StrEnum):
    wg_zimmer_ch = "wg-zimmer.ch"
    woko = "woko.ch"
    students_ch = "students.ch"


class ExampleDraft(BaseModel):
    listing_url: HttpUrl
    content: str


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

    public_transport_stark: Optional[PublicTransportConnection] = None
    bike_stark: Optional[BikeConnection] = None

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

    def to_llm_input(self, include_images: bool = True) -> list[dict[str, str]]:
        """Format listing data for LLM input."""

        # Collect relevant fields
        data = self.data_for_llm()

        # Primary text block
        output: list[dict[str, str]] = [
            {
                "type": "text",
                "text": "Listing to reply to:\n" + json.dumps(data, ensure_ascii=False),
            }
        ]

        if not include_images:
            return output

        # Embed images as base64
        for img in self.img_urls:
            enc = self._fetch_and_format_img(img)
            if enc:
                output.append(enc)

        return output

    def data_for_llm(self):
        data: dict[str, str] = {}
        for attr in (
            "beschreibung",
            "größe_in_m2",
            "datum_ab_frei",
            "datum_frei_bis",
            "miete",
        ) + tuple(self.additional_fields):
            val = getattr(self, attr, None)
            if val is not None:
                data[attr] = val.isoformat() if hasattr(val, "isoformat") else str(val)
        return data

    def _fetch_and_format_img(self, img_url: HttpUrl) -> dict[str, str] | None:
        try:
            response = requests.get(str(img_url))
            response.raise_for_status()
            return {"type": "image_url", "image_url": str(img_url)}

        except Exception as e:
            logger.info(f"loading img_url '{img_url}' failed with {e}")
            return None


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


class ListingSQL(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    url: str = SQLField(index=True, primary_key=True)
    gesehen: bool = SQLField(default=False, description="Vom User als gesehen markiert")
    gemerkt: bool = SQLField(default=False, description="Vom User gemerkt")
    status: str = SQLField(
        default="active", description="Ist das Listing noch aktuell?"
    )
    first_seen: datetime = SQLField(
        default_factory=datetime.now,
        description="Wann wurde das Listing zum ersten Mal gesehen? -> db intern",
    )
    last_seen: datetime = SQLField(
        default_factory=datetime.now,
        description="Wann wurde das Listing zuletzt im Fetch gesehen? -> db intern",
    )
    listing: str
    website: Webiste = SQLField(sa_column=Column(Enum(Webiste), nullable=False))

    @classmethod
    def from_pydantic(cls, listing: BaseListing) -> "ListingSQL":
        return cls(
            url=str(listing.url),
            gesehen=listing.gesehen,
            gemerkt=listing.gemerkt,
            status=listing.status,
            first_seen=listing.first_seen,
            last_seen=listing.last_seen,
            listing=listing.model_dump_json(),
            website=listing.website,
        )

    def to_pydantic(self) -> WGZimmerCHListing | StudentsCHListing | WokoListing:
        model = WEBSITE_TO_MODEL[self.website].model_validate_json(self.listing)
        model.gesehen = self.gesehen
        model.gemerkt = self.gemerkt
        model.status = self.status
        model.first_seen = self.first_seen
        model.last_seen = self.last_seen
        return model
