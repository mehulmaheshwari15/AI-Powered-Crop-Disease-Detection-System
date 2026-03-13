"""
models/crop_models.py
----------------------
Database table definitions for the Crop Care System.
SQLAlchemy reads these classes and creates matching tables in crop_care.db.
"""

from sqlalchemy import Column, String, Float, Integer, Text, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base


class Farmer(Base):
    """Stores farmer account information."""
    __tablename__ = "farmers"

    farmer_id   = Column(String, primary_key=True, index=True)
    name        = Column(String, nullable=False)
    phone       = Column(String, unique=True, nullable=False)
    language    = Column(String, default="en")   # e.g., 'hi', 'te', 'ta'
    region      = Column(String, nullable=True)
    created_at  = Column(DateTime, server_default=func.now())


class Field(Base):
    """A plot of land owned by a farmer."""
    __tablename__ = "fields"

    field_id       = Column(String, primary_key=True, index=True)
    farmer_id      = Column(String, nullable=False, index=True)
    field_name     = Column(String, nullable=False)          # e.g., "North Plot"
    area_in_acres  = Column(Float, nullable=True)
    soil_type      = Column(String, nullable=True)           # CLAY, LOAMY, SANDY, etc.
    irrigation_type = Column(String, nullable=True)          # DRIP, FLOOD, SPRINKLER
    latitude       = Column(Float, nullable=True)
    longitude      = Column(Float, nullable=True)
    created_at     = Column(DateTime, server_default=func.now())


class CropSeason(Base):
    """
    One record per crop planted per field per season.
    This is the central record that everything else links to.
    """
    __tablename__ = "crop_seasons"

    season_id            = Column(String, primary_key=True, index=True)
    field_id             = Column(String, nullable=False, index=True)
    farmer_id            = Column(String, nullable=False, index=True)
    crop_name            = Column(String, nullable=False)    # e.g., "Wheat"
    crop_variety         = Column(String, nullable=True)     # e.g., "HD-2967"
    sowing_date          = Column(String, nullable=False)    # ISO date: "2026-03-01"
    expected_harvest_date = Column(String, nullable=True)
    actual_harvest_date  = Column(String, nullable=True)
    current_stage        = Column(String, default="SOWING")
    # SOWING | GERMINATION | VEGETATIVE | FLOWERING | FRUITING | MATURATION | HARVESTED
    status               = Column(String, default="ACTIVE")
    # ACTIVE | COMPLETED | ABANDONED
    notes                = Column(Text, nullable=True)
    created_at           = Column(DateTime, server_default=func.now())
    updated_at           = Column(DateTime, server_default=func.now(), onupdate=func.now())


class FarmingAction(Base):
    """
    Append-only event ledger. Every farming event is recorded here forever.
    This is the most important table in the entire system.
    """
    __tablename__ = "farming_actions"

    action_id       = Column(String, primary_key=True, index=True)
    season_id       = Column(String, nullable=False, index=True)
    farmer_id       = Column(String, nullable=False, index=True)
    action_type     = Column(String, nullable=False)
    # SOWING | IRRIGATION | FERTILIZER_APPLICATION | PESTICIDE_SPRAY |
    # FUNGICIDE_SPRAY | HEALTH_OBSERVATION | DISEASE_DETECTED | TREATMENT_APPLIED |
    # HARVEST_COMPLETE | HARVEST_PARTIAL | WEEDING | PRUNING | OTHER
    action_date     = Column(String, nullable=False)        # ISO date
    quantity        = Column(Float, nullable=True)
    quantity_unit   = Column(String, nullable=True)         # "liters", "kg", "bags"
    product_name    = Column(String, nullable=True)         # fertilizer/pesticide brand
    method          = Column(String, nullable=True)         # "foliar spray", "drip"
    weather         = Column(String, nullable=True)         # SUNNY | CLOUDY | RAINY
    notes           = Column(Text, nullable=True)
    photo_path      = Column(String, nullable=True)
    ai_disease_ref  = Column(String, nullable=True)         # links to AI diagnosis
    is_synced       = Column(Boolean, default=False)        # for cloud sync tracking
    created_at      = Column(DateTime, server_default=func.now())


class Recommendation(Base):
    """System-generated farming advice sent to the farmer."""
    __tablename__ = "recommendations"

    recommendation_id  = Column(String, primary_key=True, index=True)
    season_id          = Column(String, nullable=False, index=True)
    farmer_id          = Column(String, nullable=False, index=True)
    rec_type           = Column(String, nullable=False)
    # IRRIGATION | FERTILIZER | PESTICIDE | FUNGICIDE | HARVEST | DISEASE_ALERT | GENERAL
    trigger            = Column(String, nullable=True)      # SCHEDULE | STAGE_CHANGE | AI_ALERT
    title              = Column(String, nullable=False)
    body               = Column(Text, nullable=False)
    urgency            = Column(String, default="LOW")      # LOW | MEDIUM | HIGH | CRITICAL
    is_read            = Column(Boolean, default=False)
    is_acted_upon      = Column(Boolean, default=False)
    generated_at       = Column(DateTime, server_default=func.now())
    valid_until        = Column(String, nullable=True)
