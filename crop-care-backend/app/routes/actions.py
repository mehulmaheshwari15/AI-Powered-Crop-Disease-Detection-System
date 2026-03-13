"""
routes/actions.py
------------------
API routes for logging and retrieving Farming Actions.
Every event a farmer performs is recorded here — forever.
"""

import uuid
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.models.crop_models import FarmingAction, CropSeason

router = APIRouter(prefix="/actions", tags=["Farming Actions"])


# ── Valid Action Types ────────────────────────────────────────────────────────
VALID_ACTION_TYPES = [
    "SOWING",
    "GERMINATION_OBSERVED",
    "IRRIGATION",
    "FERTILIZER_APPLICATION",
    "PESTICIDE_SPRAY",
    "FUNGICIDE_SPRAY",
    "HERBICIDE_SPRAY",
    "WEEDING",
    "PRUNING",
    "THINNING",
    "HEALTH_OBSERVATION",
    "DISEASE_DETECTED",
    "TREATMENT_APPLIED",
    "SOIL_TEST",
    "HARVEST_PARTIAL",
    "HARVEST_COMPLETE",
    "CROP_LOSS",
    "OTHER",
]


# ── Pydantic Schema ───────────────────────────────────────────────────────────

class ActionCreate(BaseModel):
    season_id: str
    farmer_id: str
    action_type: str
    action_date: str                    # Format: "YYYY-MM-DD"
    quantity: Optional[float] = None
    quantity_unit: Optional[str] = None # "liters", "kg", "bags"
    product_name: Optional[str] = None  # e.g., "Urea", "Chlorpyrifos"
    method: Optional[str] = None        # "foliar spray", "drip irrigation"
    weather: Optional[str] = None       # "SUNNY", "CLOUDY", "RAINY"
    notes: Optional[str] = None
    ai_disease_ref: Optional[str] = None  # AI diagnosis ID if action is disease-related


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/", summary="Log a farming action")
def log_action(data: ActionCreate, db: Session = Depends(get_db)):
    """
    Log any farming event — irrigation, fertilizer, spray, disease observation, etc.
    This is the most frequently used endpoint in the system.
    """
    # Validate action type
    if data.action_type not in VALID_ACTION_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action_type. Valid types: {VALID_ACTION_TYPES}"
        )

    # Make sure the crop season exists
    season = db.query(CropSeason).filter(CropSeason.season_id == data.season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="Crop season not found. Check season_id.")

    action = FarmingAction(
        action_id=str(uuid.uuid4()),
        season_id=data.season_id,
        farmer_id=data.farmer_id,
        action_type=data.action_type,
        action_date=data.action_date,
        quantity=data.quantity,
        quantity_unit=data.quantity_unit,
        product_name=data.product_name,
        method=data.method,
        weather=data.weather,
        notes=data.notes,
        ai_disease_ref=data.ai_disease_ref,
        is_synced=False,
    )
    db.add(action)
    db.commit()
    db.refresh(action)

    return {
        "message": f"Action '{data.action_type}' logged successfully!",
        "action_id": action.action_id,
        "action_date": data.action_date,
    }


@router.get("/season/{season_id}", summary="Get all farming actions for a crop season")
def get_actions_by_season(season_id: str, db: Session = Depends(get_db)):
    """Returns the complete history of all farming events for a specific crop season."""
    actions = (
        db.query(FarmingAction)
        .filter(FarmingAction.season_id == season_id)
        .order_by(FarmingAction.action_date)
        .all()
    )
    return {
        "season_id": season_id,
        "total_actions": len(actions),
        "action_log": actions,
    }


@router.get("/farmer/{farmer_id}", summary="Get recent actions by a farmer (all seasons)")
def get_actions_by_farmer(farmer_id: str, db: Session = Depends(get_db)):
    """Returns the last 50 farming actions across all seasons for a farmer."""
    actions = (
        db.query(FarmingAction)
        .filter(FarmingAction.farmer_id == farmer_id)
        .order_by(FarmingAction.created_at.desc())
        .limit(50)
        .all()
    )
    return {"farmer_id": farmer_id, "recent_actions": actions}
