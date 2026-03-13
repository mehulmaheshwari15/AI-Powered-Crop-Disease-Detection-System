"""
app/timeline.py  -  Crop Lifecycle Timeline Builder
=====================================================
This module builds the visual crop timeline returned by:
  GET /api/v1/crop-care/seasons/{season_id}/timeline

Each entry in the timeline represents a key farming event / milestone.
Status is one of:
  DONE     — the farmer logged this action around the scheduled day
  OVERDUE  — the scheduled day has passed but the action was not logged
  UPCOMING — the scheduled day has not arrived yet

How it works:
  1. CROP_MILESTONES defines the expected schedule for each crop
     (day, event label, action_type to check, optional tolerance window).
  2. build_timeline() iterates the milestones, queries the action log,
     and assigns each milestone a status.
  3. The result is a flat list of timeline entries, in chronological order.

How to add a new crop:
  - Add its milestones to CROP_MILESTONES.
  - No other code changes needed.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.crop_models import CropSeason, FarmingAction


# ═══════════════════════════════════════════════════════════════════════════════
# Crop Milestone Schedules
# ═══════════════════════════════════════════════════════════════════════════════
# Each milestone dict has:
#   day         — target day after sowing
#   event       — human-readable label
#   action_type — the FarmingAction type to check in the database
#                 (None = always DONE, used for Sowing which has no action log entry)
#   window      — ± day tolerance for "was it done around this milestone?" (default 7)

CROP_MILESTONES: dict[str, list[dict]] = {

    "wheat": [
        {"day": 0,   "event": "Sowing",                  "action_type": None,                       "window": 0},
        {"day": 5,   "event": "First Irrigation",         "action_type": "IRRIGATION",               "window": 5},
        {"day": 10,  "event": "Germination Check",        "action_type": "HEALTH_OBSERVATION",       "window": 5},
        {"day": 21,  "event": "Nitrogen Fertilizer",      "action_type": "FERTILIZER_APPLICATION",   "window": 7},
        {"day": 21,  "event": "First Weeding",            "action_type": "WEEDING",                  "window": 7},
        {"day": 30,  "event": "Second Irrigation",        "action_type": "IRRIGATION",               "window": 7},
        {"day": 45,  "event": "Pesticide Spray",          "action_type": "PESTICIDE_SPRAY",          "window": 7},
        {"day": 60,  "event": "Fungicide Spray",          "action_type": "FUNGICIDE_SPRAY",          "window": 7},
        {"day": 90,  "event": "Pre-Harvest Observation",  "action_type": "HEALTH_OBSERVATION",       "window": 7},
        {"day": 100, "event": "Harvest Preparation",      "action_type": "OTHER",                    "window": 7},
        {"day": 120, "event": "Harvest",                  "action_type": "HARVEST_COMPLETE",         "window": 7},
    ],

    "rice": [
        {"day": 0,   "event": "Transplanting / Sowing",   "action_type": None,                       "window": 0},
        {"day": 5,   "event": "First Irrigation",         "action_type": "IRRIGATION",               "window": 3},
        {"day": 10,  "event": "Germination Check",        "action_type": "HEALTH_OBSERVATION",       "window": 5},
        {"day": 20,  "event": "Nitrogen Fertilizer",      "action_type": "FERTILIZER_APPLICATION",   "window": 7},
        {"day": 25,  "event": "Weeding",                  "action_type": "WEEDING",                  "window": 7},
        {"day": 35,  "event": "Pesticide Spray",          "action_type": "PESTICIDE_SPRAY",          "window": 7},
        {"day": 50,  "event": "Flowering Irrigation",     "action_type": "IRRIGATION",               "window": 5},
        {"day": 60,  "event": "Fungicide Spray",          "action_type": "FUNGICIDE_SPRAY",          "window": 7},
        {"day": 80,  "event": "Pre-Harvest Observation",  "action_type": "HEALTH_OBSERVATION",       "window": 7},
        {"day": 85,  "event": "Drain Field",              "action_type": "IRRIGATION",               "window": 5},
        {"day": 90,  "event": "Harvest",                  "action_type": "HARVEST_COMPLETE",         "window": 5},
    ],

    "maize": [
        {"day": 0,   "event": "Sowing",                   "action_type": None,                       "window": 0},
        {"day": 4,   "event": "First Irrigation",         "action_type": "IRRIGATION",               "window": 3},
        {"day": 7,   "event": "Germination Check",        "action_type": "HEALTH_OBSERVATION",       "window": 3},
        {"day": 21,  "event": "Nitrogen Fertilizer",      "action_type": "FERTILIZER_APPLICATION",   "window": 7},
        {"day": 21,  "event": "Weeding",                  "action_type": "WEEDING",                  "window": 7},
        {"day": 30,  "event": "Fall Armyworm Scout",      "action_type": "PESTICIDE_SPRAY",          "window": 7},
        {"day": 40,  "event": "Silking Irrigation",       "action_type": "IRRIGATION",               "window": 5},
        {"day": 50,  "event": "Fungicide Spray",          "action_type": "FUNGICIDE_SPRAY",          "window": 7},
        {"day": 70,  "event": "Maturity Check",           "action_type": "HEALTH_OBSERVATION",       "window": 7},
        {"day": 80,  "event": "Harvest",                  "action_type": "HARVEST_COMPLETE",         "window": 5},
    ],

    "tomato": [
        {"day": 0,   "event": "Transplanting",            "action_type": None,                       "window": 0},
        {"day": 2,   "event": "First Irrigation",         "action_type": "IRRIGATION",               "window": 2},
        {"day": 8,   "event": "Seedling Check",           "action_type": "HEALTH_OBSERVATION",       "window": 4},
        {"day": 21,  "event": "Stake / Trellis Support",  "action_type": "OTHER",                    "window": 7},
        {"day": 25,  "event": "NPK Fertilizer",           "action_type": "FERTILIZER_APPLICATION",   "window": 7},
        {"day": 25,  "event": "Weeding",                  "action_type": "WEEDING",                  "window": 7},
        {"day": 35,  "event": "Pesticide Spray",          "action_type": "PESTICIDE_SPRAY",          "window": 7},
        {"day": 45,  "event": "Fungicide Spray",          "action_type": "FUNGICIDE_SPRAY",          "window": 7},
        {"day": 55,  "event": "Fruit Set Check",          "action_type": "HEALTH_OBSERVATION",       "window": 7},
        {"day": 65,  "event": "Fruit Borer Scout",        "action_type": "PESTICIDE_SPRAY",          "window": 7},
        {"day": 75,  "event": "Harvest Check",            "action_type": "HEALTH_OBSERVATION",       "window": 7},
        {"day": 80,  "event": "First Harvest",            "action_type": "HARVEST_PARTIAL",          "window": 7},
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# Status Helper
# ═══════════════════════════════════════════════════════════════════════════════

def _milestone_status(
    season_id: str,
    action_type: Optional[str],
    milestone_day: int,
    window: int,
    days_elapsed: int,
    sowing_date: str,
    db: Session,
) -> str:
    """
    Returns the status for one milestone.

    Logic:
      • action_type is None  → always "DONE" (e.g. the Sowing milestone itself)
      • days_elapsed < milestone_day  → "UPCOMING"
      • days_elapsed >= milestone_day → query the action log within ±window days
          of the milestone target date:
          - found  → "DONE"
          - not found → "OVERDUE"
    """
    if action_type is None:
        return "DONE"       # Sowing marker — season creation implies sowing happened

    # Always query the database for the action within the target window
    sow = date.fromisoformat(sowing_date)
    target_date  = sow + timedelta(days=milestone_day)
    window_start = (target_date - timedelta(days=window)).isoformat()
    window_end   = (target_date + timedelta(days=window)).isoformat()

    print(f"DEBUG TIMELINE: checking '{action_type}' for milestone_day {milestone_day}. "
          f"Window: {window_start} to {window_end}. season: {season_id}")

    # Map milestone action_type to allowed database types
    allowed_types = [action_type]
    if action_type == "HEALTH_OBSERVATION":
        allowed_types = ["HEALTH_OBSERVATION", "DISEASE_DETECTED"]
    elif action_type in ["HARVEST_COMPLETE", "HARVEST_PARTIAL"]:
        allowed_types = ["HARVEST_PARTIAL", "HARVEST_COMPLETE"]

    action = (
        db.query(FarmingAction)
        .filter(
            FarmingAction.season_id  == season_id,
            FarmingAction.action_type.in_(allowed_types),
            FarmingAction.action_date >= window_start,
            FarmingAction.action_date <= window_end,
        )
        .first()
    )
    
    if action:
        print(f"DEBUG TIMELINE: found action! {action.action_date}")
        return "DONE"
    else:
        print(f"DEBUG TIMELINE: action NOT found.")
        
    # If not done, determine if it's overdue or upcoming
    if days_elapsed > milestone_day:
        return "OVERDUE"
    else:
        return "UPCOMING"


# ═══════════════════════════════════════════════════════════════════════════════
# Public Entry Point
# ═══════════════════════════════════════════════════════════════════════════════

def build_timeline(season: CropSeason, db: Session) -> list[dict]:
    """
    Build the full crop lifecycle timeline for a given season.

    Returns a list of timeline entries in chronological order:
        [
          {"day": 0,  "event": "Sowing",           "status": "DONE"},
          {"day": 21, "event": "Nitrogen Fertilizer", "status": "OVERDUE"},
          {"day": 30, "event": "Second Irrigation", "status": "UPCOMING"},
          ...
        ]
    """
    crop_key = season.crop_name.lower().strip()
    milestones = CROP_MILESTONES.get(crop_key)

    # Fallback for crops not yet in CROP_MILESTONES
    if not milestones:
        return [{
            "day":    0,
            "event":  "Sowing",
            "status": "DONE",
            "note":   f"Detailed timeline for {season.crop_name} is not yet configured.",
        }]

    sowing_date  = season.sowing_date
    days_elapsed = (date.today() - date.fromisoformat(sowing_date)).days

    timeline = []
    for m in milestones:
        status = _milestone_status(
            season_id     = season.season_id,
            action_type   = m["action_type"],
            milestone_day = m["day"],
            window        = m.get("window", 7),
            days_elapsed  = days_elapsed,
            sowing_date   = sowing_date,
            db            = db,
        )
        # Calculate the calendar date for this milestone
        target_date = (
            date.fromisoformat(sowing_date) + timedelta(days=m["day"])
        ).isoformat()

        timeline.append({
            "day":         m["day"],
            "target_date": target_date,
            "event":       m["event"],
            "status":      status,
        })

    return timeline
