# 🌾 Crop Care System — System Design Document
**Module**: Crop Care System  
**Project**: AI-Powered Smart Crop Disease Detection Platform  
**Role**: Intelligent Digital Farming Assistant  
**Version**: 1.0  
**Date**: March 2026

---

## 1. Overview

The **Crop Care System** is the lifecycle management core of the platform. It acts as a persistent, intelligent digital farming assistant that tracks every farming event from the first seed planted to the final harvest. It maintains complete historical records, generates context-aware agronomic recommendations, and integrates with the AI Disease Detection module to close the loop between diagnosis and treatment action.

### Key Design Principles
| Principle | Rationale |
|---|---|
| **Offline-First** | Rural farmers may have no internet connectivity for days |
| **Persistent Records** | Every event is logged permanently; nothing is deleted unless by the farmer |
| **Crop-Lifecycle Awareness** | All logic is governed by real crop growth stages |
| **Simplicity** | UI/UX must be operable by low-literacy users; voice/icon-driven inputs |
| **Multilingual** | All farmer-facing text uses the platform's language layer |
| **Low Compute Footprint** | Runs on entry-level Android devices (2GB RAM, Android 8+) |

---

## 2. Core Modules

```
┌────────────────────────────────────────────────────┐
│                  Crop Care System                  │
│                                                    │
│  ┌──────────────┐    ┌───────────────────────────┐ │
│  │  Crop        │    │  Farming Action           │ │
│  │  Registry    │◄───│  Logger                   │ │
│  └──────┬───────┘    └───────────────────────────┘ │
│         │                                          │
│  ┌──────▼───────┐    ┌───────────────────────────┐ │
│  │  Lifecycle   │───►│  Recommendation           │ │
│  │  Engine      │    │  Engine                   │ │
│  └──────┬───────┘    └───────────────────────────┘ │
│         │                                          │
│  ┌──────▼───────┐    ┌───────────────────────────┐ │
│  │  Alert &     │    │  AI Disease               │ │
│  │  Reminder    │    │  Bridge (External)        │ │
│  │  Service     │    └───────────────────────────┘ │
│  └──────────────┘                                  │
└────────────────────────────────────────────────────┘
```

---

## 3. Data Models

### 3.1 Farmer Profile
```json
{
  "farmer_id": "UUID",
  "name": "string",
  "phone": "string",
  "language_code": "hi | en | te | ta | mr | ...",
  "region": "string",
  "state": "string",
  "created_at": "ISO8601 timestamp",
  "last_active": "ISO8601 timestamp"
}
```

---

### 3.2 Field (Plot of Land)
A farmer may manage multiple fields. Each field is tracked independently.

```json
{
  "field_id": "UUID",
  "farmer_id": "UUID (FK)",
  "field_name": "string (e.g. 'North Plot')",
  "area_in_acres": "float",
  "soil_type": "enum: CLAY | LOAMY | SANDY | SILT | CHALKY | PEATY",
  "irrigation_type": "enum: DRIP | FLOOD | SPRINKLER | RAIN_FED",
  "geo_location": {
    "latitude": "float",
    "longitude": "float"
  },
  "created_at": "ISO8601 timestamp"
}
```

---

### 3.3 Crop Season (Central Record)
This is the primary entity. Every crop planted on a field in a season gets its own `CropSeason` record. It tracks the entire lifecycle from sowing to harvest.

```json
{
  "season_id": "UUID",
  "field_id": "UUID (FK)",
  "farmer_id": "UUID (FK)",
  "crop_name": "string (e.g. 'Wheat', 'Paddy', 'Tomato')",
  "crop_variety": "string (e.g. 'HD-2967', 'Pusa 44')",
  "sowing_date": "ISO8601 date",
  "expected_harvest_date": "ISO8601 date (system-computed)",
  "actual_harvest_date": "ISO8601 date | null",
  "current_stage": "enum: SOWING | GERMINATION | VEGETATIVE | FLOWERING | FRUITING | MATURATION | HARVESTED",
  "status": "enum: ACTIVE | COMPLETED | ABANDONED",
  "seed_source": "string (optional)",
  "seeds_per_acre": "integer (optional)",
  "row_spacing_cm": "float (optional)",
  "plant_spacing_cm": "float (optional)",
  "notes": "string (optional)",
  "created_at": "ISO8601 timestamp",
  "updated_at": "ISO8601 timestamp"
}
```

> **Design Note**: The `current_stage` is auto-updated by the Lifecycle Engine based on `sowing_date` and the crop's known growth timeline. The farmer can also manually advance the stage.

---

### 3.4 Farming Action Log
This is the **event ledger** — an immutable, append-only record of every farming action performed. This is the system's most critical dataset.

```json
{
  "action_id": "UUID",
  "season_id": "UUID (FK)",
  "farmer_id": "UUID (FK)",
  "action_type": "enum (see below)",
  "action_date": "ISO8601 date",
  "action_time": "ISO8601 time (optional)",
  "quantity": "float | null",
  "quantity_unit": "string | null (e.g. 'liters', 'kg', 'bags')",
  "product_name": "string | null (fertilizer/pesticide brand name)",
  "method": "string | null (e.g. 'foliar spray', 'drip')",
  "weather_condition": "enum: SUNNY | CLOUDY | RAINY | WINDY | null",
  "temperature_celsius": "float | null",
  "notes": "string | null",
  "photo_url": "string | null (local or cloud path)",
  "ai_disease_ref": "UUID | null (links to AI diagnosis result if applicable)",
  "is_synced": "boolean (for offline sync tracking)",
  "created_at": "ISO8601 timestamp"
}
```

#### Action Type Enum
| Code | Description |
|---|---|
| `SOWING` | Seeds planted |
| `GERMINATION_OBSERVED` | Farmer confirmed seedlings emerged |
| `IRRIGATION` | Watering event |
| `FERTILIZER_APPLICATION` | Chemical or organic fertilizer applied |
| `PESTICIDE_SPRAY` | Insecticide, acaricide applied |
| `FUNGICIDE_SPRAY` | Antifungal treatment applied |
| `HERBICIDE_SPRAY` | Weed killer applied |
| `THINNING` | Removal of weak seedlings |
| `WEEDING` | Manual or mechanical weeding |
| `PRUNING` | Plant pruning/trimming |
| `HEALTH_OBSERVATION` | General crop health observation/note |
| `DISEASE_DETECTED` | AI Disease Detection result logged |
| `TREATMENT_APPLIED` | Treatment applied post disease detection |
| `SOIL_TEST` | Soil sample taken, results logged |
| `HARVEST_PARTIAL` | Partial/staggered harvesting |
| `HARVEST_COMPLETE` | Full harvest completed |
| `CROP_LOSS` | Crop loss event logged (storm, pest, etc.) |
| `OTHER` | Free-form event |

---

### 3.5 Recommendation Record
A log of all system-generated recommendations sent to the farmer.

```json
{
  "recommendation_id": "UUID",
  "season_id": "UUID (FK)",
  "farmer_id": "UUID (FK)",
  "recommendation_type": "enum: IRRIGATION | FERTILIZER | PESTICIDE | FUNGICIDE | HARVEST | DISEASE_ALERT | GENERAL",
  "trigger": "enum: SCHEDULE | STAGE_CHANGE | AI_ALERT | WEATHER | FARMER_QUERY",
  "title": "string (localized)",
  "body": "string (localized)",
  "urgency": "enum: LOW | MEDIUM | HIGH | CRITICAL",
  "is_read": "boolean",
  "is_acted_upon": "boolean",
  "generated_at": "ISO8601 timestamp",
  "valid_until": "ISO8601 timestamp | null"
}
```

---

## 4. Crop Lifecycle Engine

### 4.1 Concept
The Lifecycle Engine is the system's central intelligence. It models the biological growth stages of a crop and knows what farming activities are due at each stage.

### 4.2 Growth Stage Timeline (Example: Wheat — 120 Days)
```
Day 0        Day 7        Day 21       Day 45       Day 75       Day 95       Day 120
  │            │            │            │            │            │            │
SOWING ──► GERMINATION ──► VEGETATIVE ──► TILLERING ──► FLOWERING ──► GRAIN_FILL ──► HARVEST
  │            │            │            │            │            │
  └─ Sow seeds └─ Check     └─ 1st Fert  └─ 2nd Fert  └─ Fungicide  └─ Stop
     at correct  germination   Irrigation   Irrigation   if humidity    irrigation
     depth/spacing             + Urea       + Potash     is high
```

### 4.3 Crop Stage Database Schema
```json
{
  "crop_config_id": "UUID",
  "crop_name": "string",
  "variety": "string",
  "total_days": "integer",
  "stages": [
    {
      "stage_name": "SOWING",
      "start_day": 0,
      "end_day": 6,
      "description": "Seed germination period",
      "recommended_actions": [
        {
          "action": "IRRIGATION",
          "detail": "Light irrigation immediately after sowing",
          "timing_hint": "Day 0-1"
        }
      ]
    },
    {
      "stage_name": "GERMINATION",
      "start_day": 7,
      "end_day": 20,
      "description": "Seedling emergence and establishment",
      "recommended_actions": [
        {
          "action": "HEALTH_OBSERVATION",
          "detail": "Check germination percentage",
          "timing_hint": "Day 10"
        },
        {
          "action": "IRRIGATION",
          "detail": "Light irrigation every 5 days",
          "timing_hint": "Days 12, 17"
        }
      ]
    }
    // ... stages continue for VEGETATIVE, FLOWERING, FRUITING, MATURATION
  ]
}
```

### 4.4 Lifecycle Engine Logic (Pseudocode)
```python
def compute_current_stage(sowing_date, crop_config):
    days_elapsed = (today - sowing_date).days
    for stage in crop_config.stages:
        if stage.start_day <= days_elapsed <= stage.end_day:
            return stage
    return HARVESTED

def get_due_actions(season, crop_config):
    stage = compute_current_stage(season.sowing_date, crop_config)
    already_done = get_logged_actions(season.season_id)
    due = []
    for action in stage.recommended_actions:
        if action.action_type not in already_done:
            due.append(action)
    return due

def advance_stage_if_needed(season):
    new_stage = compute_current_stage(season.sowing_date, crop_config)
    if new_stage != season.current_stage:
        update_season_stage(season.season_id, new_stage)
        trigger_stage_change_recommendations(season, new_stage)
```

---

## 5. Recommendation Engine

### 5.1 How It Works
The Recommendation Engine runs on a **scheduled basis** (daily, on app open, or on any farming action logged). It evaluates the current crop stage, historical actions, and external signals to produce contextual advice.

### 5.2 Recommendation Triggers

| Trigger | Example |
|---|---|
| **Time-based schedule** | "It has been 8 days since last irrigation. Wheat at this stage needs water every 7 days." |
| **Stage transition** | "Your crop has entered the Flowering stage. Stop applying Nitrogen fertilizer now." |
| **AI Disease Alert** | "AI detected early signs of Powdery Mildew. Apply Sulfur-based fungicide within 48 hours." |
| **Action gap detection** | "No fertilizer application recorded in past 21 days. 2nd dose of Urea is typically due now." |
| **Pre-harvest signal** | "Grain fill is complete. Withhold irrigation for 10 days before harvest." |
| **Weather-triggered (future)** | "Rain forecasted tomorrow. Postpone pesticide spray to avoid washoff." |

### 5.3 Recommendation Priority Matrix
```
CRITICAL  → AI-confirmed disease treatment required (< 48h window)
HIGH      → Irrigation overdue by 2+ days; critical stage fertilizer missed
MEDIUM    → Scheduled pesticide/fungicide window approaching
LOW       → General advisory; best-practice tips for current stage
```

### 5.4 Recommendation Generation Logic (Pseudocode)
```python
def generate_recommendations(season):
    recommendations = []
    stage = lifecycle_engine.get_current_stage(season)
    
    # 1. Check action gaps
    for expected_action in stage.recommended_actions:
        last_done = get_last_action_date(season, expected_action.type)
        days_overdue = (today - last_done).days - expected_action.interval_days
        if days_overdue > 0:
            recommendations.append(
                Recommendation(
                    type=expected_action.type,
                    urgency=HIGH if days_overdue > 2 else MEDIUM,
                    body=f"{expected_action.type} is {days_overdue} days overdue."
                )
            )
    
    # 2. Check AI disease alerts pending action
    unresolved_diseases = get_unactioned_ai_alerts(season)
    for disease in unresolved_diseases:
        recommendations.append(
            Recommendation(
                type=DISEASE_ALERT,
                urgency=CRITICAL,
                body=f"AI detected {disease.name}. Treatment: {disease.treatment}"
            )
        )
    
    # 3. Stage-change guidance
    if stage_changed_today(season):
        recommendations.append(stage_guidance_message(stage))
    
    return sorted(recommendations, key=lambda r: r.urgency, reverse=True)
```

---

## 6. AI Disease Detection Integration

The Crop Care System integrates with the **AI Disease Detection module** via an internal bridge interface.

### Flow
```
Farmer opens camera in App
        │
        ▼
AI Disease Detection Module
  → Analyzes leaf image
  → Returns: disease_name, confidence, severity, treatment
        │
        ▼
Crop Care System — AI Disease Bridge
  → Creates DISEASE_DETECTED action log entry
  → Links diagnosis result to active CropSeason
  → Triggers CRITICAL recommendation to farmer
  → Schedules follow-up: "Did you apply treatment? Mark as done."
        │
        ▼
Farmer marks treatment applied
  → TREATMENT_APPLIED action logged
  → Recommendation marked as acted_upon
```

### Disease-to-Action Mapping (Sample)
| Detected Disease | Crop | Recommended Treatment Action |
|---|---|---|
| Powdery Mildew | Wheat | Sulfur 80WP @ 2.5g/L foliar spray |
| Brown Rust | Wheat | Tebuconazole @ 1ml/L spray |
| Bacterial Blight | Paddy | Copper Oxychloride + Streptomycin spray |
| Early Blight | Tomato | Mancozeb 75WP @ 2.5g/L spray |
| Leaf Curl Virus | Cotton | Remove infected plants; spray Imidacloprid |

---

## 7. Database Architecture

### 7.1 Local Database (SQLite — Offline First)
```sql
-- Core tables stored locally on device

CREATE TABLE farmers (farmer_id TEXT PRIMARY KEY, name TEXT, phone TEXT, ...);
CREATE TABLE fields (field_id TEXT PRIMARY KEY, farmer_id TEXT, area_in_acres REAL, ...);
CREATE TABLE crop_seasons (season_id TEXT PRIMARY KEY, field_id TEXT, crop_name TEXT, current_stage TEXT, ...);
CREATE TABLE farming_actions (
    action_id TEXT PRIMARY KEY,
    season_id TEXT,
    action_type TEXT,
    action_date TEXT,
    quantity REAL,
    product_name TEXT,
    notes TEXT,
    is_synced INTEGER DEFAULT 0,  -- 0=pending, 1=synced
    created_at TEXT
);
CREATE TABLE recommendations (recommendation_id TEXT PRIMARY KEY, season_id TEXT, body TEXT, urgency TEXT, is_read INTEGER DEFAULT 0, ...);
CREATE TABLE crop_configs (crop_config_id TEXT PRIMARY KEY, crop_name TEXT, stages_json TEXT);
```

### 7.2 Cloud Sync Strategy
```
Device (SQLite) ──[on connectivity]──► Cloud DB (PostgreSQL / Firebase)

Sync Rules:
  - farming_actions where is_synced = 0  →  push to cloud
  - recommendations generated server-side  →  pull to device
  - crop_configs (crop knowledge base)  →  pull on app install / weekly update
  - Conflict resolution: Last-write-wins on action records (actions are append-only)
  - Sync frequency: On app open + background every 6 hours if connected
```

---

## 8. API Specification

### Base URL: `/api/v1/crop-care/`

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/seasons` | Create new crop season |
| `GET` | `/seasons/{season_id}` | Get season details + current stage |
| `GET` | `/seasons?farmer_id=X` | List all seasons for a farmer |
| `PATCH` | `/seasons/{season_id}/stage` | Manually advance crop stage |
| `POST` | `/seasons/{season_id}/actions` | Log a farming action |
| `GET` | `/seasons/{season_id}/actions` | Get full action history |
| `GET` | `/seasons/{season_id}/recommendations` | Get current recommendations |
| `PATCH` | `/recommendations/{rec_id}/read` | Mark recommendation as read |
| `PATCH` | `/recommendations/{rec_id}/acted` | Mark recommendation as acted upon |
| `GET` | `/crops/configs` | Get crop knowledge base |
| `POST` | `/ai-bridge/disease-result` | Receive AI diagnosis, create action log + recommendation |

---

## 9. Alert & Reminder Service

Farmers receive **push notifications** (where connectivity exists) and **in-app alerts** for:

- Irrigation due reminders
- Fertilizer schedule reminders
- Disease treatment follow-ups (CRITICAL urgency)
- Stage advancement confirmations
- Harvest readiness alerts
- Inactivity alerts: "No activity logged in 5 days — is your crop okay?"

> **Offline Mode**: If offline, alerts are stored locally and shown the next time the farmer opens the app. A persistent badge on the home screen shows how many pending recommendations exist.

---

## 10. Crop Health Score (Dashboard Feature)

A computed score (0–100) that provides farmers a quick snapshot of crop health.

```
Health Score = f(
    irrigation_compliance    × 0.25,
    fertilizer_compliance    × 0.20,
    pesticide_compliance     × 0.15,
    disease_status           × 0.30,   ← Most heavily weighted
    days_since_last_obs      × 0.10
)
```

| Score | Status | Indicator Color |
|---|---|---|
| 80–100 | Excellent | 🟢 Green |
| 60–79 | Good | 🟡 Yellow |
| 40–59 | Needs Attention | 🟠 Orange |
| 0–39 | At Risk | 🔴 Red |

---

## 11. Farmer-Facing Workflow (User Journey)

```
1. REGISTER & SET UP FIELD
   Farmer onboards → adds field (area, soil type, irrigation type)

2. START A CROP SEASON
   Selects crop name + variety → enters sowing date
   System computes: expected harvest date, stage timeline, first set of recommendations

3. DAILY DASHBOARD
   Farmer opens app → sees Crop Health Score
   Sees "Today's Tasks": pending recommendations for the day
   One-tap logging: "Water √", "Spray √", "Observed crop √"

4. LOG FARMING ACTIONS
   Farmer taps action type → fills quantity/product → submits
   System records event, updates compliance score, removes related recommendation

5. AI DISEASE SCAN
   Farmer taps camera icon → scans leaf
   Result flows into Crop Care System → generates CRITICAL recommendation if disease found

6. RECEIVE ALERTS
   Push notifications + in-app banners guide timing of next activities

7. HARVEST & CLOSE SEASON
   Farmer logs HARVEST_COMPLETE → season marked as COMPLETED
   System generates full season summary (actions done, yield if entered, diseases encountered)

8. HISTORICAL RECORDS
   All past seasons remain accessible
   Farmer can compare: "Last year wheat yield vs this year"
```

---

## 12. Technology Stack (Suggested)

| Layer | Technology |
|---|---|
| **Mobile App** | Flutter (cross-platform Android/iOS) |
| **Local DB** | SQLite via `sqflite` package |
| **Backend API** | FastAPI (Python) |
| **Cloud DB** | PostgreSQL (via Supabase or AWS RDS) |
| **Auth** | Firebase Auth (phone OTP, no password needed) |
| **Push Notifications** | Firebase Cloud Messaging (FCM) |
| **AI Model Bridge** | REST call to ML inference service (FastAPI + TensorFlow Serving) |
| **Sync Queue** | Custom SQLite-based queue with retry logic |

---

## 13. Key Design Decisions & Rationale

| Decision | Rationale |
|---|---|
| **Append-only action log** | Farming history must be forensically accurate. No edits; corrections are new entries. |
| **Stage-based recommendation engine** | Real agriculture is stage-driven; blanket timers don't account for crop biology. |
| **SQLite offline-first** | Rural India has 40–60% of farming areas with poor connectivity. Data must not be lost. |
| **No password login** | Farmers use phone OTP. Remembering passwords is a barrier. |
| **One-tap action logging** | Multi-step forms will be abandoned. Quickly log; add details later. |
| **Crop Health Score** | A single number is more actionable for low-literacy users than raw event lists. |
| **season_id as central FK** | All data hangs off the crop season. This enables perfect per-season analytics. |

---

## 14. Future Enhancements (Post-Hackathon)

- 🌦 **Live weather API integration** — Adjust irrigation recommendations based on rain forecast
- 🛰 **Remote sensing integration** — NDVI satellite imagery to detect crop stress at field level
- 📊 **Yield prediction model** — Estimate yield based on historical actions and current stage compliance
- 🧑‍🤝‍🧑 **Community benchmarking** — Compare your crop health with nearby farmers growing the same crop
- 🗣 **Voice input** — Farmers can log actions by speaking ("Maine aaj 20 liter dawa dali")
- 📈 **Season-over-season analytics** — Which fertilizers, varieties gave best results historically

---

*Document prepared for HackJKLU 5.0 — AI-Powered Smart Crop Disease Detection Platform*
