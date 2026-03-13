"""
database.py
-----------
Sets up the SQLite database connection using SQLAlchemy.
SQLite stores everything in a single file (crop_care.db) — no separate DB server needed!
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# This tells SQLAlchemy to use SQLite and save the database to a file called crop_care.db
DATABASE_URL = "sqlite:///./crop_care.db"

# Create the database engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}  # Required for SQLite with FastAPI
)

# SessionLocal is used to talk to the database
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Base class that all our database models will inherit from
class Base(DeclarativeBase):
    pass


# Dependency — used in route functions to get a DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
