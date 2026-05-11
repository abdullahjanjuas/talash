"""
database.py
===========
SQLAlchemy engine and session management for SQLite.

On Streamlit Community Cloud the filesystem is read-only except for /tmp,
so we detect writability and fall back to /tmp/talash.db automatically.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base

# Determine a writable location for the SQLite database
# Streamlit Cloud / Hugging Face Spaces have read-only filesystems
_DB_DIR = "/tmp" if not os.access(".", os.W_OK) else "."
DATABASE_URL = f"sqlite:///{_DB_DIR}/talash.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}  # required for Streamlit multi-threading
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False
)


def create_tables():
    """
    Create all tables defined in models.py (idempotent — safe to call on every start).
    """
    Base.metadata.create_all(bind=engine)