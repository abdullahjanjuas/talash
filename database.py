# This file handles the connection to our SQLite database and actually creates tables in db as defined in models.py.
# SQLite stores everything in a single file called talash.db

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base  # import all our table definitions

# Path to db
DATABASE_URL = "sqlite:///./talash.db"

# Actual connection to db
# Using multiple threads for streamlit
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

# SessionLocal is a factory that creates database sessions
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,  # we control when to commit changes
    autoflush=False
)


def create_tables():
    """
    Creates all tables defined in models.py inside talash.db
    """
    Base.metadata.create_all(bind=engine)