"""
routes/recommendations.py
--------------------------
API routes for system-generated farming recommendations.

The heavy lifting is done by app.engine — this file only handles:
  - HTTP plumbing (routing, request/response)
  - Persisting manual recommendations to the DB
  - Mark-as-read / mark-as-acted endpoints
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.crop_models import Recommendation, CropSeason
from app.engine import run_engine   # ← the new rule-based engine

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/{season_id}", summary="Get smart recommendations for a crop season")
def get_recommendations(season_id: str, db: Session = Depends(get_db)):
    """
    Runs the rule-based recommendation engine and returns:
      - Recommendations sorted by urgency (CRITICAL → HIGH → MEDIUM → LOW)
      - Crop health score (0–100) with status label and deduction breakdown
      - Auto-detected current growth stage
      - Days since sowing

    Health status labels: EXCELLENT (91–100), GOOD (71–90), FAIR (41–70), POOR (0–40).
    """
    season = db.query(CropSeason).filter(CropSeason.season_id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")

    result = run_engine(season, db)

    return {
        "season_id":             season_id,
        "crop_name":             season.crop_name,
        "current_stage":         result["current_stage"],
        "sowing_date":           season.sowing_date,
        "expected_harvest_date": season.expected_harvest_date,
        "days_since_sowing":     result["days_since_sowing"],
        # ── Health Score ──────────────────────────────────────────────────────
        "crop_health_score":     result["crop_health_score"],
        "health_status":         result["health_status"],
        "score_details":         result["score_details"],
        # ── Recommendations ───────────────────────────────────────────────────
        "total_recommendations": len(result["recommendations"]),
        "recommendations":       result["recommendations"],
    }



@router.post("/manual", summary="Save a manual recommendation (e.g. from AI disease detection)")
def save_recommendation(
    season_id: str,
    farmer_id: str,
    title: str,
    body: str,
    urgency: str = "LOW",
    rec_type: str = "GENERAL",
    db: Session = Depends(get_db),
):
    """
    Stores a custom recommendation in the database.
    Used by the AI Disease Detection bridge to persist disease alerts.
    """
    rec = Recommendation(
        recommendation_id=str(uuid.uuid4()),
        season_id=season_id,
        farmer_id=farmer_id,
        rec_type=rec_type,
        trigger="AI_ALERT",
        title=title,
        body=body,
        urgency=urgency,
        is_read=False,
        is_acted_upon=False,
    )
    db.add(rec)
    db.commit()
    return {"message": "Recommendation saved", "recommendation_id": rec.recommendation_id}


@router.patch("/{rec_id}/read", summary="Mark a recommendation as read")
def mark_read(rec_id: str, db: Session = Depends(get_db)):
    rec = db.query(Recommendation).filter(Recommendation.recommendation_id == rec_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    rec.is_read = True
    db.commit()
    return {"message": "Marked as read"}


@router.patch("/{rec_id}/acted", summary="Mark a recommendation as acted upon")
def mark_acted(rec_id: str, db: Session = Depends(get_db)):
    rec = db.query(Recommendation).filter(Recommendation.recommendation_id == rec_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    rec.is_acted_upon = True
    db.commit()
    return {"message": "Marked as acted upon"}
