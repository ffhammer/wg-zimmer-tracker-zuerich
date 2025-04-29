from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, HttpUrl, ConfigDict
from typing import Literal


class ListingScraped(BaseModel):
    model_config = ConfigDict(extra="ignore")
    aufgegeben_datum: Optional[datetime] = Field(
        None, description="das datum wo das inserat aufgegeb wurde"
    )
    datum_ab_frei: Optional[datetime] = Field(
        None, description="das datum ab dem das inserat frei ist"
    )
    miete: Optional[float] = Field(None, description="miete in schweizer franken")
    adresse: Optional[str] = Field(None, description="einfach ganzer adress string")
    url: Optional[HttpUrl] = Field(None, description="die url zu dem specifischen post")
    img_url: Optional[HttpUrl] = Field(None, description="URL des Vorschaubildes")


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

    # Eindeutige ID für Streamlit-Keys etc. (kann einfach die URL sein)
    @property
    def id(self) -> str:
        return str(self.url)

    # Hilfsmethode zum Aktualisieren aus einem neuen Scrape
    def update_from_scraped(self, scraped: "ListingScraped"):
        # Update fields that might change (though unlikely for WGZimmer)
        self.miete = scraped.miete
        self.adresse = scraped.adresse
        self.img_url = scraped.img_url
        self.aufgegeben_datum = scraped.aufgegeben_datum
        self.datum_ab_frei = scraped.datum_ab_frei
        # Update internal status
        self.last_seen = datetime.now()
        self.status = "active"  # Mark as active again if it was deleted
