from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


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
