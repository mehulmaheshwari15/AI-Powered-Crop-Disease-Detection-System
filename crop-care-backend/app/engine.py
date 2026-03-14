"""
app/engine.py  -  Crop Care Recommendation Engine
====================================================
Sections in this file:
  1. Data types          — Recommendation, RuleContext
  2. CROP_SCHEDULES      — Stage day-ranges per crop (auto-detection table)
  3. Stage helpers       — auto_detect_stage(), auto_update_stage()
  4. Urgency helper      — urgency_from_overdue()
  5. Rule factories      — Functions that generate rule functions for any crop:
                           irrigation, fertilizer, weeding, fungicide, pesticide,
                           observation.  Using factories avoids copy-paste across crops.
  6. Custom rules        — Crop-specific rules that can't be expressed by factories
  7. CROP_RULES registry — Maps (crop, stage) → [list of rule functions]
  8. Health score        — calculate_health_score()
  9. run_engine()        — Public entry point called by the recommendations route
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.models.crop_models import CropSeason, FarmingAction


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Data Types
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Recommendation:
    """One farming advice item produced by a single rule function."""
    type: str           # e.g. "IRRIGATION", "FERTILIZER", "FUNGICIDE_SPRAY"
    urgency: str        # LOW | MEDIUM | HIGH | CRITICAL
    message: str        # Plain-language message shown to the farmer
    days_overdue: int = 0


@dataclass
class RuleContext:
    """
    Shared context passed into every rule function.
    All DB queries are centralised here so rule functions stay clean.
    """
    season: CropSeason
    db: Session
    today: date = field(default_factory=date.today)

    def days_since_sowing(self) -> int:
        return (self.today - date.fromisoformat(self.season.sowing_date)).days

    def last_action_date(self, action_type: str) -> Optional[date]:
        """Most recent date this action_type was logged, or None."""
        row = (
            self.db.query(FarmingAction)
            .filter(
                FarmingAction.season_id == self.season.season_id,
                FarmingAction.action_type == action_type,
            )
            .order_by(FarmingAction.action_date.desc())
            .first()
        )
        return date.fromisoformat(row.action_date) if row else None

    def days_since_last(self, action_type: str) -> Optional[int]:
        last = self.last_action_date(action_type)
        return (self.today - last).days if last else None

    def has_ever_done(self, action_type: str) -> bool:
        return self.last_action_date(action_type) is not None

    def within_interval(self, action_type: str, interval_days: int) -> bool:
        """
        Duplicate-prevention check.
        Returns True if this action was done within the last `interval_days` days.
        When True, the calling rule should return None (skip the recommendation).
        """
        days = self.days_since_last(action_type)
        return days is not None and days < interval_days


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Crop Stage Schedules
# ═══════════════════════════════════════════════════════════════════════════════
# Defines day-range boundaries for each growth stage per crop.
# auto_detect_stage() scans this table to figure out the current stage.
#
# To add a new crop: add a list of stage dicts here.
# Stage lists must be in chronological order. Use to_day=9999 for the last stage.

CROP_SCHEDULES: dict[str, list[dict]] = {
    "wheat": [
        {"name": "GERMINATION", "from_day": 0,   "to_day": 7},
        {"name": "VEGETATIVE",  "from_day": 8,   "to_day": 30},
        {"name": "FLOWERING",   "from_day": 31,  "to_day": 60},
        {"name": "MATURATION",  "from_day": 61,  "to_day": 100},
        {"name": "HARVESTED",   "from_day": 101, "to_day": 9999},
    ],
    "rice": [
        {"name": "GERMINATION", "from_day": 0,   "to_day": 10},
        {"name": "VEGETATIVE",  "from_day": 11,  "to_day": 40},
        {"name": "FLOWERING",   "from_day": 41,  "to_day": 60},
        {"name": "MATURATION",  "from_day": 61,  "to_day": 90},
        {"name": "HARVESTED",   "from_day": 91,  "to_day": 9999},
    ],
    "paddy": [  # alias for rice
        {"name": "GERMINATION", "from_day": 0,   "to_day": 10},
        {"name": "VEGETATIVE",  "from_day": 11,  "to_day": 40},
        {"name": "FLOWERING",   "from_day": 41,  "to_day": 60},
        {"name": "MATURATION",  "from_day": 61,  "to_day": 90},
        {"name": "HARVESTED",   "from_day": 91,  "to_day": 9999},
    ],
    "maize": [
        {"name": "GERMINATION", "from_day": 0,   "to_day": 7},
        {"name": "VEGETATIVE",  "from_day": 8,   "to_day": 35},
        {"name": "FLOWERING",   "from_day": 36,  "to_day": 55},
        {"name": "MATURATION",  "from_day": 56,  "to_day": 80},
        {"name": "HARVESTED",   "from_day": 81,  "to_day": 9999},
    ],
    "tomato": [
        {"name": "GERMINATION", "from_day": 0,   "to_day": 10},
        {"name": "VEGETATIVE",  "from_day": 11,  "to_day": 30},
        {"name": "FLOWERING",   "from_day": 31,  "to_day": 50},
        {"name": "FRUITING",    "from_day": 51,  "to_day": 70},
        {"name": "MATURATION",  "from_day": 71,  "to_day": 90},
        {"name": "HARVESTED",   "from_day": 91,  "to_day": 9999},
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Stage Detection & Auto-Update
# ═══════════════════════════════════════════════════════════════════════════════

def auto_detect_stage(crop_name: str, days_elapsed: int) -> Optional[str]:
    """Map days elapsed since sowing → growth stage name using CROP_SCHEDULES."""
    schedule = CROP_SCHEDULES.get(crop_name.lower().strip())
    if not schedule:
        return None
    for s in schedule:
        if s["from_day"] <= days_elapsed <= s["to_day"]:
            return s["name"]
    return None


def auto_update_stage(season: CropSeason, db: Session, days_elapsed: int) -> str:
    """
    Compute the correct stage, persist to DB if changed, return stage name.
    Called automatically every time the recommendations endpoint is used.
    """
    detected = auto_detect_stage(season.crop_name, days_elapsed)
    if detected and detected != season.current_stage:
        season.current_stage = detected
        db.add(season)
        db.commit()
        db.refresh(season)
    return season.current_stage


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Urgency Helper
# ═══════════════════════════════════════════════════════════════════════════════

def urgency_from_overdue(days_overdue: int) -> str:
    """Convert overdue-days count to urgency label."""
    if days_overdue <= 0:   return "LOW"
    if days_overdue <= 2:   return "MEDIUM"
    if days_overdue <= 5:   return "HIGH"
    return "CRITICAL"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Rule Factories
# ═══════════════════════════════════════════════════════════════════════════════
# A factory is a function that RETURNS a rule function.
# This avoids copy-pasting the same logic for every crop.
#
# Usage example:
#   rice_veg_irrigation = _irrigation(crop="rice", stage="VEGETATIVE", interval=5)
#   # Now rice_veg_irrigation is a rule function usable in CROP_RULES.

RuleFn = Callable[["RuleContext"], Optional[Recommendation]]


def _irrigation(crop: str, stage: str, interval: int) -> RuleFn:
    """
    Factory: creates an irrigation rule for any crop/stage with a given interval.
    DUPLICATE PREVENTION: rule returns None if watered within `interval` days.
    """
    def rule(ctx: RuleContext) -> Optional[Recommendation]:
        if ctx.within_interval("IRRIGATION", interval):
            return None                         # Done recently — skip
        days = ctx.days_since_last("IRRIGATION")
        if days is None:
            return Recommendation(
                type="IRRIGATION", urgency="HIGH",
                message=(
                    f"No irrigation recorded. {crop.capitalize()} at {stage.lower()} "
                    f"stage needs watering every {interval} days."
                ),
            )
        overdue = days - interval
        return Recommendation(
            type="IRRIGATION",
            urgency=urgency_from_overdue(overdue),
            days_overdue=overdue,
            message=(
                f"Last irrigation was {days} day(s) ago. "
                f"{crop.capitalize()} at {stage.lower()} stage requires watering every {interval} days."
            ),
        )
    rule.__name__ = f"{crop}_{stage.lower()}_irrigation"
    return rule


def _fertilizer(crop: str, stage: str, due_day: int, advice: str) -> RuleFn:
    """
    Factory: recommends fertilizer if it has never been applied (yet.
    DUPLICATE PREVENTION: returns None once any fertilizer action is logged.
    `advice` is the specific product/method recommendation for this crop.
    """
    def rule(ctx: RuleContext) -> Optional[Recommendation]:
        if ctx.has_ever_done("FERTILIZER_APPLICATION"):
            return None                         # Already applied — skip
        days = ctx.days_since_sowing()
        if days < due_day:
            return None                         # Not yet due
        overdue = days - due_day
        return Recommendation(
            type="FERTILIZER",
            urgency=urgency_from_overdue(overdue) if overdue > 0 else "MEDIUM",
            days_overdue=overdue,
            message=f"No fertilizer applied yet for {crop}. {advice}",
        )
    rule.__name__ = f"{crop}_{stage.lower()}_fertilizer"
    return rule


def _weeding(crop: str, stage: str, due_day: int) -> RuleFn:
    """
    Factory: recommends weeding if not yet done past `due_day`.
    DUPLICATE PREVENTION: returns None once any WEEDING action is logged.
    """
    def rule(ctx: RuleContext) -> Optional[Recommendation]:
        if ctx.has_ever_done("WEEDING"):
            return None
        days = ctx.days_since_sowing()
        if days < due_day:
            return None
        overdue = days - due_day
        return Recommendation(
            type="WEEDING",
            urgency=urgency_from_overdue(overdue),
            days_overdue=overdue,
            message=(
                f"No weeding done yet. Weeds compete with {crop} for water and nutrients. "
                "Remove manually or apply a suitable selective herbicide."
            ),
        )
    rule.__name__ = f"{crop}_{stage.lower()}_weeding"
    return rule


def _fungicide(crop: str, stage: str, interval: int, disease_tip: str) -> RuleFn:
    """
    Factory: recommends fungicide spray at a given repeat interval.
    DUPLICATE PREVENTION: returns None if sprayed within `interval` days.
    `disease_tip` names the main disease threat for context.
    """
    def rule(ctx: RuleContext) -> Optional[Recommendation]:
        if ctx.within_interval("FUNGICIDE_SPRAY", interval):
            return None
        days = ctx.days_since_last("FUNGICIDE_SPRAY")
        if days is None:
            return Recommendation(
                type="FUNGICIDE_SPRAY", urgency="MEDIUM",
                message=(
                    f"No fungicide sprayed yet during {stage.lower()} stage. "
                    f"{crop.capitalize()} is vulnerable to {disease_tip}. "
                    "Apply a suitable fungicide preventively."
                ),
            )
        overdue = days - interval
        return Recommendation(
            type="FUNGICIDE_SPRAY",
            urgency=urgency_from_overdue(overdue),
            days_overdue=overdue,
            message=(
                f"Last fungicide spray was {days} day(s) ago. "
                f"Repeat every {interval} days to protect {crop} against {disease_tip}."
            ),
        )
    rule.__name__ = f"{crop}_{stage.lower()}_fungicide"
    return rule


def _pesticide(crop: str, stage: str, interval: int, pest_tip: str) -> RuleFn:
    """
    Factory: recommends pesticide spray at a given repeat interval.
    DUPLICATE PREVENTION: returns None if sprayed within `interval` days.
    """
    def rule(ctx: RuleContext) -> Optional[Recommendation]:
        if ctx.within_interval("PESTICIDE_SPRAY", interval):
            return None
        days = ctx.days_since_last("PESTICIDE_SPRAY")
        if days is None:
            return Recommendation(
                type="PESTICIDE_SPRAY", urgency="MEDIUM",
                message=(
                    f"No pesticide applied during {stage.lower()} stage. "
                    f"Monitor {crop} for {pest_tip} and spray if detected."
                ),
            )
        overdue = days - interval
        return Recommendation(
            type="PESTICIDE_SPRAY",
            urgency=urgency_from_overdue(overdue),
            days_overdue=overdue,
            message=(
                f"Last pesticide spray was {days} day(s) ago. "
                f"Protect {crop} from {pest_tip} every {interval} days."
            ),
        )
    rule.__name__ = f"{crop}_{stage.lower()}_pesticide"
    return rule


def _observation(crop: str, stage: str, due_day: int, check_tip: str) -> RuleFn:
    """
    Factory: reminds the farmer to perform a crop health observation.
    DUPLICATE PREVENTION: returns None if an observation was logged within 7 days.
    """
    def rule(ctx: RuleContext) -> Optional[Recommendation]:
        if ctx.within_interval("HEALTH_OBSERVATION", 7):
            return None
        days = ctx.days_since_sowing()
        if days < due_day:
            return None
        overdue = days - due_day
        return Recommendation(
            type="HEALTH_OBSERVATION",
            urgency=urgency_from_overdue(overdue),
            days_overdue=overdue,
            message=(
                f"Day {days}: {check_tip}"
            ),
        )
    rule.__name__ = f"{crop}_{stage.lower()}_observation"
    return rule


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Custom Crop-Specific Rules
# (rules that need logic beyond what the factories above can express)
# ═══════════════════════════════════════════════════════════════════════════════

# ── Wheat ─────────────────────────────────────────────────────────────────────

def wheat_flowering_no_excess_nitrogen(ctx: RuleContext) -> Optional[Recommendation]:
    """
    Warn if nitrogen fertilizer was applied recently during FLOWERING.
    Excess nitrogen at this stage causes lodging and poor grain fill.
    """
    days = ctx.days_since_last("FERTILIZER_APPLICATION")
    if days is not None and days <= 7:
        return Recommendation(
            type="FERTILIZER", urgency="HIGH",
            message=(
                f"Fertilizer was applied {days} day(s) ago. WARNING: excess nitrogen "
                "during wheat flowering causes stem lodging and poor grain filling. "
                "Do NOT apply more nitrogen until grain fill is complete."
            ),
        )
    return None


def wheat_maturation_harvest_prep(ctx: RuleContext) -> Optional[Recommendation]:
    """Harvest preparation reminder fires after day 95 for wheat (120-day crop)."""
    if ctx.days_since_sowing() < 95:
        return None
    return Recommendation(
        type="OTHER", urgency="LOW",
        message=(
            f"Day {ctx.days_since_sowing()}: Harvest approaching — "
            "service your combine/harvester, clean storage bags, and arrange transport."
        ),
    )


def wheat_maturation_reduce_irrigation(ctx: RuleContext) -> Optional[Recommendation]:
    """Alert if wheat is being irrigated too close to harvest."""
    days = ctx.days_since_last("IRRIGATION")
    if days is not None and days < 10:
        return Recommendation(
            type="IRRIGATION", urgency="MEDIUM",
            message=(
                f"Irrigation done {days} day(s) ago. Stop irrigating wheat 10–12 days "
                "before harvest so grains dry evenly and fungal diseases are prevented."
            ),
        )
    return None


# ── Rice ──────────────────────────────────────────────────────────────────────

def rice_vegetative_flooding(ctx: RuleContext) -> Optional[Recommendation]:
    """
    Rice in vegetative stage grows best with 5–7 cm of standing water.
    Remind the farmer to maintain field flooding if no irrigation logged recently.
    """
    days = ctx.days_since_last("IRRIGATION")
    if days is None or days >= 3:
        return Recommendation(
            type="IRRIGATION", urgency="HIGH",
            days_overdue=days - 3 if days else 0,
            message=(
                "Rice fields need 5–7 cm of standing water during vegetative growth. "
                f"{'No irrigation recorded.' if days is None else f'Last water top-up was {days} day(s) ago.'} "
                "Top up water levels every 3 days or maintain continuous flooding."
            ),
        )
    return None


# ── Maize ─────────────────────────────────────────────────────────────────────

def maize_flowering_critical_water(ctx: RuleContext) -> Optional[Recommendation]:
    """
    Silking / tasselling is the single most critical stage for maize.
    Water stress during this window can cause 40–60% yield loss.
    """
    if ctx.within_interval("IRRIGATION", 5):
        return None
    days = ctx.days_since_last("IRRIGATION")
    prefix = f"Last irrigation was {days} day(s) ago. " if days else "No irrigation recorded. "
    return Recommendation(
        type="IRRIGATION", urgency="CRITICAL",
        days_overdue=(days - 5) if days and days >= 5 else 0,
        message=(
            prefix
            + "Silking / tasselling stage is the most water-sensitive period in maize. "
            "Even one missed irrigation now can cut yield by 40–60%. Water immediately."
        ),
    )


# ── Tomato ────────────────────────────────────────────────────────────────────

def tomato_vegetative_staking(ctx: RuleContext) -> Optional[Recommendation]:
    """
    Tomato plants need stakes or trellis support installed by day 21
    to prevent stem breakage as the plant grows heavy.
    """
    days = ctx.days_since_sowing()
    if days < 21 or ctx.has_ever_done("OTHER"):   # OTHER used as proxy for staking
        return None
    return Recommendation(
        type="OTHER", urgency="MEDIUM",
        message=(
            f"Day {days}: Install bamboo stakes or trellis support for tomato plants now. "
            "Unsupported plants break easily as they grow heavy with fruit. "
            "Tie each plant loosely to the stake every 15–20 cm of growth."
        ),
    )


def tomato_fruiting_fruit_check(ctx: RuleContext) -> Optional[Recommendation]:
    """Remind the farmer to check fruit development and look for blossom-end rot."""
    if ctx.within_interval("HEALTH_OBSERVATION", 5):
        return None
    return Recommendation(
        type="HEALTH_OBSERVATION", urgency="MEDIUM",
        message=(
            "Tomato is in fruiting stage. Check for blossom-end rot (dark sunken patch "
            "at the base of fruit — caused by calcium deficiency or irregular watering). "
            "Also look for fruit borer damage and remove affected fruits immediately."
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Crop Rules Registry
# ═══════════════════════════════════════════════════════════════════════════════
# Maps: crop_name (lowercase) → { stage_name → [rule functions] }
#
# Factory calls are inlined here for readability — each line is self-documenting:
#   _irrigation("rice", "VEGETATIVE", 3) → "irrigate rice every 3 days in VEGETATIVE"

CROP_RULES: dict[str, dict[str, list]] = {

    # ── WHEAT (120-day crop) ──────────────────────────────────────────────────
    "wheat": {
        "GERMINATION": [
            _irrigation("wheat", "GERMINATION", interval=7),
            _observation("wheat", "GERMINATION", due_day=7,
                check_tip="Check germination percentage. Wheat should show ≥85% emergence by day 10."),
        ],
        "VEGETATIVE": [
            _fertilizer("wheat", "VEGETATIVE", due_day=21,
                advice="Apply Urea @ 60 kg/acre, broadcast evenly, then irrigate lightly."),
            _irrigation("wheat", "VEGETATIVE", interval=10),
            _weeding("wheat", "VEGETATIVE", due_day=21),
        ],
        "FLOWERING": [
            wheat_flowering_no_excess_nitrogen,
            _irrigation("wheat", "FLOWERING", interval=10),
            _fungicide("wheat", "FLOWERING", interval=14,
                disease_tip="Powdery Mildew and Brown Rust"),
        ],
        "MATURATION": [
            wheat_maturation_reduce_irrigation,
            _observation("wheat", "MATURATION", due_day=90,
                check_tip="Check wheat for maturity: golden straw, firm grains, hollow stems."),
            wheat_maturation_harvest_prep,
        ],
    },

    # ── RICE (90-day crop) ────────────────────────────────────────────────────
    "rice": {
        "GERMINATION": [
            _irrigation("rice", "GERMINATION", interval=3),
            _observation("rice", "GERMINATION", due_day=8,
                check_tip="Check rice germination and seedling health. Thin overcrowded spots."),
        ],
        "VEGETATIVE": [
            _fertilizer("rice", "VEGETATIVE", due_day=20,
                advice="Apply Urea @ 50 kg/acre. Top-dress after establishing 5–7 cm water depth."),
            rice_vegetative_flooding,   # custom: rice needs standing water, not drip
            _weeding("rice", "VEGETATIVE", due_day=25),
        ],
        "FLOWERING": [
            _irrigation("rice", "FLOWERING", interval=4),
            _pesticide("rice", "FLOWERING", interval=14,
                pest_tip="stem borer and leaf folder (look for dead hearts and white ears)"),
            _fungicide("rice", "FLOWERING", interval=14,
                disease_tip="Blast and Sheath Blight"),
        ],
        "MATURATION": [
            _observation("rice", "MATURATION", due_day=80,
                check_tip="Check rice maturity: 80% of grains should be golden. Drain field 7 days before harvest."),
        ],
    },

    # alias rice → paddy
    "paddy": {},    # populated below after class definition

    # ── MAIZE (80-day crop) ───────────────────────────────────────────────────
    "maize": {
        "GERMINATION": [
            _irrigation("maize", "GERMINATION", interval=4),
            _observation("maize", "GERMINATION", due_day=7,
                check_tip="Count germinated plants. Maize should show ≥90% emergence by day 7."),
        ],
        "VEGETATIVE": [
            _fertilizer("maize", "VEGETATIVE", due_day=21,
                advice="Apply Urea @ 65 kg/acre in two splits: half now, half at knee-height stage."),
            _irrigation("maize", "VEGETATIVE", interval=7),
            _weeding("maize", "VEGETATIVE", due_day=21),
            _pesticide("maize", "VEGETATIVE", interval=14,
                pest_tip="Fall Armyworm (look for window-pane damage on leaves and frass in whorls)"),
        ],
        "FLOWERING": [
            maize_flowering_critical_water,   # custom: silking stage, CRITICAL urgency
            _fungicide("maize", "FLOWERING", interval=14,
                disease_tip="Northern Corn Leaf Blight and Common Rust"),
        ],
        "MATURATION": [
            _observation("maize", "MATURATION", due_day=70,
                check_tip="Check maize maturity: husk should be dry and brown, kernels hard and dented."),
        ],
    },

    # ── TOMATO (90-day crop) ──────────────────────────────────────────────────
    "tomato": {
        "GERMINATION": [
            _irrigation("tomato", "GERMINATION", interval=2),
            _observation("tomato", "GERMINATION", due_day=8,
                check_tip="Check seedling emergence and thin weak plants. Keep soil moist but not waterlogged."),
        ],
        "VEGETATIVE": [
            _fertilizer("tomato", "VEGETATIVE", due_day=21,
                advice="Apply NPK 19:19:19 @ 30 g per plant or Urea + SSP mix for strong stem growth."),
            _irrigation("tomato", "VEGETATIVE", interval=4),
            _weeding("tomato", "VEGETATIVE", due_day=21),
            tomato_vegetative_staking,    # custom: install stakes by day 21
        ],
        "FLOWERING": [
            _irrigation("tomato", "FLOWERING", interval=4),
            _pesticide("tomato", "FLOWERING", interval=10,
                pest_tip="whitefly and aphids (they spread Tomato Yellow Leaf Curl Virus)"),
            _fungicide("tomato", "FLOWERING", interval=10,
                disease_tip="Early Blight and Late Blight"),
        ],
        "FRUITING": [
            _irrigation("tomato", "FRUITING", interval=4),
            tomato_fruiting_fruit_check,  # custom: blossom-end rot + fruit borer check
            _pesticide("tomato", "FRUITING", interval=10,
                pest_tip="fruit borer (Helicoverpa) — spray immediately if tunnelling observed"),
        ],
        "MATURATION": [
            _observation("tomato", "MATURATION", due_day=75,
                check_tip="Harvest tomatoes when uniformly red/yellow and firm. Check daily to avoid over-ripening."),
        ],
    },
}

# Populate paddy as a copy of rice rules
CROP_RULES["paddy"] = CROP_RULES["rice"]

# Sort order: lower number = shown first
_URGENCY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Crop Health Score
# ═══════════════════════════════════════════════════════════════════════════════

# Irrigation intervals per crop (days) — used for scoring
_CROP_IRRIGATION_INTERVALS = {
    "wheat": 10, "rice": 3, "paddy": 3, "maize": 7, "tomato": 4,
}

def calculate_health_score(season: CropSeason, db: Session,
                            days_elapsed: int, stage: str) -> dict:
    """
    Computes a 0–100 Crop Health Score based on how well maintenance is tracked.

    Scoring:
      Start at 100.
      -10  if irrigation is overdue (last water > interval × 1.5 days ago, or never)
      -15  if no fertilizer applied by day 21+ in VEGETATIVE or later
      -10  if no weeding done past day 21
      - 5  if no health observation in FLOWERING/FRUITING in last 14 days
      + 5  bonus if irrigation is up to date (done within interval)
      Clamped to [0, 100].

    Health status labels:
      91–100 → EXCELLENT
      71–90  → GOOD
      41–70  → FAIR
       0–40  → POOR
    """
    ctx = RuleContext(season=season, db=db)
    score = 100
    deductions: list[str] = []
    bonuses: list[str] = []

    # ── Irrigation check ──────────────────────────────────────────────────────
    interval = _CROP_IRRIGATION_INTERVALS.get(season.crop_name.lower(), 7)
    days_irr = ctx.days_since_last("IRRIGATION")

    if days_irr is None:
        score -= 10
        deductions.append("No irrigation logged")
    elif days_irr > interval * 1.5:
        overdue = int(days_irr - interval)
        score -= 10
        deductions.append(f"Irrigation overdue by {overdue} day(s)")
    else:
        # Irrigation is on track — give a bonus
        score = min(100, score + 5)
        bonuses.append("Irrigation up to date (+5)")

    # ── Fertilizer check (expected by day 21 in VEGETATIVE or later) ──────────
    veg_or_later = stage not in ("GERMINATION", "SOWING")
    if days_elapsed >= 21 and veg_or_later and not ctx.has_ever_done("FERTILIZER_APPLICATION"):
        score -= 15
        deductions.append("No fertilizer applied in vegetative stage (-15)")

    # ── Weeding check (expected by day 21) ────────────────────────────────────
    if days_elapsed >= 21 and not ctx.has_ever_done("WEEDING"):
        score -= 10
        deductions.append("No weeding done past day 21 (-10)")

    # ── Health observation in key stages ──────────────────────────────────────
    if stage in ("FLOWERING", "FRUITING", "MATURATION"):
        obs_days = ctx.days_since_last("HEALTH_OBSERVATION")
        if obs_days is None or obs_days > 14:
            score -= 5
            deductions.append("No crop observation in last 14 days (-5)")

    # ── Clamp and label ───────────────────────────────────────────────────────
    score = max(0, min(100, score))

    if score >= 91:   status = "EXCELLENT"
    elif score >= 71: status = "GOOD"
    elif score >= 41: status = "FAIR"
    else:             status = "POOR"

    return {
        "crop_health_score": score,
        "health_status":     status,
        "score_details": {
            "deductions": deductions,
            "bonuses":    bonuses,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Public Entry Point
# ═══════════════════════════════════════════════════════════════════════════════

def run_engine(season: CropSeason, db: Session) -> dict:
    """
    Called by GET /recommendations/{season_id}.

    Steps:
      1. Compute days since sowing.
      2. Auto-detect and persist the correct growth stage.
      3. Run applicable rule functions for this crop + stage.
      4. Calculate crop health score.
      5. Sort by urgency and return a single structured dict.
    """
    today        = date.today()
    days_elapsed = (today - date.fromisoformat(season.sowing_date)).days

    # Step 1 & 2: auto-detect + save stage
    current_stage = auto_update_stage(season, db, days_elapsed)

    # Step 3: run rules
    crop_key    = season.crop_name.lower().strip()
    rule_map    = CROP_RULES.get(crop_key, {})
    stage_rules = rule_map.get(current_stage, [])

    ctx = RuleContext(season=season, db=db, today=today)
    results: list[Recommendation] = []

    if stage_rules:
        for rule_fn in stage_rules:
            rec = rule_fn(ctx)
            if rec is not None:
                results.append(rec)
    else:
        # Fallback advisory for unsupported crops/stages
        results = [_make_generic_rec(season.crop_name, current_stage)]

    results.sort(key=lambda r: _URGENCY_ORDER.get(r.urgency, 99))

    # Step 4: health score
    health = calculate_health_score(season, db, days_elapsed, current_stage)

    return {
        "days_since_sowing":  days_elapsed,
        "current_stage":      current_stage,
        "crop_health_score":  health["crop_health_score"],
        "health_status":      health["health_status"],
        "score_details":      health["score_details"],
        "recommendations": [
            {
                "type":         r.type,
                "urgency":      r.urgency,
                "message":      r.message,
                "days_overdue": r.days_overdue,
            }
            for r in results
        ],
    }


def _make_generic_rec(crop_name: str, stage: str) -> Recommendation:
    """Fallback recommendation for crops/stages not yet in CROP_RULES."""
    if stage == "HARVESTED":
        return Recommendation(
            type="OTHER", urgency="LOW",
            message=(
                f"Your {crop_name} crop has been harvested. "
                "Record your yield and consider a soil test before the next season."
            ),
        )
    return Recommendation(
        type="HEALTH_OBSERVATION", urgency="LOW",
        message=(
            f"No specific rules configured for {crop_name} at {stage} stage yet. "
            "Continue logging all farming activities and monitor crop health regularly."
        ),
    )
