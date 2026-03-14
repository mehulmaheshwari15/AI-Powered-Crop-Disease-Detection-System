"""
routes/seasons.py
------------------
API routes for managing Crop Seasons.
A crop season is the core record — everything is linked to it.
"""

import uuid
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.models.crop_models import CropSeason
from app.timeline import build_timeline

router = APIRouter(prefix="/seasons", tags=["Crop Seasons"])


# ── Pydantic Schemas (data validation) ──────────────────────────────────────

class SeasonCreate(BaseModel):
    field_id: str
    farmer_id: str
    crop_name: str
    crop_variety: Optional[str] = None
    sowing_date: str            # Format: "YYYY-MM-DD"
    notes: Optional[str] = None


class SeasonStageUpdate(BaseModel):
    current_stage: str          # e.g., "GERMINATION", "VEGETATIVE", "FLOWERING"


# ── Helper: Estimate harvest date based on crop type ────────────────────────

CROP_DURATIONS = {
    "wheat":    120,
    "paddy":    135,
    "rice":     120,
    "maize":    90,
    "tomato":   80,
    "cotton":   180,
    "soybean":  100,
    "mustard":  110,
    "potato":   90,
    "onion":    120,
}

def estimate_harvest_date(crop_name: str, sowing_date_str: str) -> str:
    sowing = date.fromisoformat(sowing_date_str)
    days = CROP_DURATIONS.get(crop_name.lower(), 120)   # default 120 days
    harvest = sowing + timedelta(days=days)
    return harvest.isoformat()


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/", summary="Start a new crop season")
def create_season(data: SeasonCreate, db: Session = Depends(get_db)):
    """
    Call this when a farmer plants a new crop.
    The system automatically calculates the expected harvest date.
    """
    harvest_date = estimate_harvest_date(data.crop_name, data.sowing_date)

    season = CropSeason(
        season_id=str(uuid.uuid4()),
        field_id=data.field_id,
        farmer_id=data.farmer_id,
        crop_name=data.crop_name,
        crop_variety=data.crop_variety,
        sowing_date=data.sowing_date,
        expected_harvest_date=harvest_date,
        current_stage="SOWING",
        status="ACTIVE",
        notes=data.notes,
    )
    db.add(season)
    db.commit()
    db.refresh(season)
    return {
        "message": f"Crop season started for {data.crop_name}!",
        "season_id": season.season_id,
        "expected_harvest_date": harvest_date,
        "current_stage": "SOWING",
    }


@router.get("/{season_id}", summary="Get details of a specific crop season")
def get_season(season_id: str, db: Session = Depends(get_db)):
    season = db.query(CropSeason).filter(CropSeason.season_id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")

    # Compute how many days since sowing
    sowing = date.fromisoformat(season.sowing_date)
    days_elapsed = (date.today() - sowing).days

    return {
        "season_id": season.season_id,
        "crop_name": season.crop_name,
        "crop_variety": season.crop_variety,
        "sowing_date": season.sowing_date,
        "expected_harvest_date": season.expected_harvest_date,
        "actual_harvest_date": season.actual_harvest_date,
        "current_stage": season.current_stage,
        "status": season.status,
        "days_elapsed_since_sowing": days_elapsed,
        "notes": season.notes,
    }


@router.get("/", summary="List all crop seasons for a farmer")
def list_seasons(farmer_id: str, db: Session = Depends(get_db)):
    seasons = db.query(CropSeason).filter(CropSeason.farmer_id == farmer_id).all()
    return {"farmer_id": farmer_id, "total_seasons": len(seasons), "seasons": seasons}


@router.patch("/{season_id}/stage", summary="Update crop growth stage")
def update_stage(season_id: str, data: SeasonStageUpdate, db: Session = Depends(get_db)):
    """Farmer or system can manually advance the crop to the next growth stage."""
    valid_stages = ["SOWING", "GERMINATION", "VEGETATIVE", "FLOWERING", "FRUITING", "MATURATION", "HARVESTED"]
    if data.current_stage not in valid_stages:
        raise HTTPException(status_code=400, detail=f"Invalid stage. Must be one of: {valid_stages}")

    season = db.query(CropSeason).filter(CropSeason.season_id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")

    season.current_stage = data.current_stage
    if data.current_stage == "HARVESTED":
        season.status = "COMPLETED"
        season.actual_harvest_date = date.today().isoformat()

    db.commit()
    return {"message": f"Stage updated to {data.current_stage}", "season_id": season_id}


@router.get("/{season_id}/timeline", summary="Get full crop lifecycle timeline")
def get_timeline(season_id: str, db: Session = Depends(get_db)):
    """
    Returns the complete crop lifecycle timeline showing every scheduled farming
    milestone and whether it was completed, is overdue, or is still upcoming.

    Status values:
      DONE     — the action was logged within the expected window
      OVERDUE  — the scheduled day has passed but no action was logged
      UPCOMING — the scheduled day is still in the future

    Useful for displaying a visual crop journey tracker in the mobile app.
    """
    season = db.query(CropSeason).filter(CropSeason.season_id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")

    sowing = date.fromisoformat(season.sowing_date)
    days_elapsed = (date.today() - sowing).days
    timeline = build_timeline(season, db)

    # Count milestones by status for a summary badge
    done     = sum(1 for t in timeline if t["status"] == "DONE")
    overdue  = sum(1 for t in timeline if t["status"] == "OVERDUE")
    upcoming = sum(1 for t in timeline if t["status"] == "UPCOMING")

    return {
        "season_id":         season_id,
        "crop_name":         season.crop_name,
        "sowing_date":       season.sowing_date,
        "days_since_sowing": days_elapsed,
        "current_stage":     season.current_stage,
        "milestone_summary": {
            "total":    len(timeline),
            "done":     done,
            "overdue":  overdue,
            "upcoming": upcoming,
        },
        "timeline": timeline,
    }
