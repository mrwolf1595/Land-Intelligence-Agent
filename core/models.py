from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime

class ParsedMessage(BaseModel):
    """A classified WhatsApp message."""
    message_id: str
    group_name: str
    sender_phone: str
    sender_name: str
    raw_text: str
    timestamp: datetime
    msg_type: Literal["offer", "request", "irrelevant"]

    property_type: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    area_sqm: Optional[float] = None
    price_sar: Optional[float] = None
    price_negotiable: bool = False
    description: Optional[str] = None

    source: str = "whatsapp"
    source_group: Optional[str] = None


class Match(BaseModel):
    """A matched request-offer pair."""
    match_id: str
    request: ParsedMessage
    offer: ParsedMessage
    match_score: float
    match_reasoning: str
    created_at: datetime = datetime.now()
    broker_notified: bool = False
    broker_action: Optional[str] = None


class LandOpportunity(BaseModel):
    """A high-value land from platform scraping."""
    listing_id: str
    source: str
    title: str
    city: str
    district: Optional[str] = None
    area_sqm: Optional[float] = None
    price_sar: float
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    image_urls: Optional[str] = None
    source_url: str
    scraped_at: datetime = datetime.now()

    analysis: Optional[dict] = None
    financial: Optional[dict] = None
    pdf_path: Optional[str] = None
    processed: bool = False
