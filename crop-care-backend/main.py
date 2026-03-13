"""
main.py — Entry point for the Crop Care System FastAPI Server
--------------------------------------------------------------
Run this file to start the local development server.
Command: uvicorn main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.routes import seasons, actions, recommendations, dev

# ── Create all database tables (runs on startup) ──────────────────────────────
# This automatically creates the crop_care.db file and all tables
# the first time you run the server. Safe to run every time.
Base.metadata.create_all(bind=engine)

# ── Initialize FastAPI App ─────────────────────────────────────────────────────
app = FastAPI(
    title="🌾 Crop Care System API",
    description="""
## AI-Powered Smart Crop Disease Detection — Crop Care Module

This backend manages the **complete lifecycle** of a farmer's crop:

- 🌱 **Crop Seasons** — Start tracking from the first seed planted
- 📋 **Farming Actions** — Log every event: irrigation, fertilizer, sprays, disease detection
- 💡 **Recommendations** — Smart advice based on crop stage and action history
- 🔗 **AI Disease Bridge** — Connect AI diagnosis results to treatment tracking
    """,
    version="1.0.0",
    contact={
        "name": "Crop Care Team",
    }
)

# ── CORS Middleware ────────────────────────────────────────────────────────────
# Allows the mobile app / frontend to call this API from any origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # In production: replace with your app's domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register all route modules ─────────────────────────────────────────────────
app.include_router(seasons.router,        prefix="/api/v1/crop-care")
app.include_router(actions.router,        prefix="/api/v1/crop-care")
app.include_router(recommendations.router, prefix="/api/v1/crop-care")
app.include_router(dev.router,            prefix="/api/v1/crop-care")


# ── Root health check ──────────────────────────────────────────────────────────
@app.get("/", tags=["Health Check"])
def root():
    return {
        "status": "✅ Crop Care System is running!",
        "message": "Visit /docs to explore the API",
        "api_base": "/api/v1/crop-care",
    }


@app.get("/health", tags=["Health Check"])
def health_check():
    return {"status": "healthy", "service": "Crop Care System", "version": "1.0.0"}
