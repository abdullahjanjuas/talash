"""
models.py
==========
SQLAlchemy ORM models defining the database schema for TALASH.

Each class maps to a table in talash.db. The inheritance from
declarative_base() lets SQLAlchemy auto-generate CREATE TABLE statements
via create_tables() in database.py.

Relationships:
  - Candidate (1) ──> Education (many)
  - Candidate (1) ──> Experience (many)
  - Candidate (1) ──> Publication (many)
  - Candidate (1) ──> Skill (many)
  - Candidate (1) ──> Patent (many)
  - Candidate (1) ──> Book (many)
  - Candidate (1) ──> Project (many)
  - Candidate (1) ──> AnalysisCache (many)
"""

from sqlalchemy import Column, Integer, String, Float, Text
from sqlalchemy.orm import declarative_base

# Base is the parent class all our table classes inherit from.
# SQLAlchemy uses it to track all registered models and generate DDL.
Base = declarative_base()


class Candidate(Base):
    """Root entity — one row per CV uploaded."""
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    address = Column(String, nullable=True)
    cv_filename = Column(String, nullable=True)  # original PDF filename


class Education(Base):
    """Each degree or academic qualification a candidate has earned."""
    __tablename__ = "education"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, nullable=False)  # FK to candidates.id

    level = Column(String, nullable=True)         # e.g. "Bachelors", "PhD"
    degree = Column(String, nullable=True)        # e.g. "BSc Computer Science"
    institution = Column(String, nullable=True)
    cgpa = Column(Float, nullable=True)           # stored as float for arithmetic
    start_year = Column(String, nullable=True)    # string to handle "2018-2019"
    end_year = Column(String, nullable=True)
    percentage = Column(Float, nullable=True)     # for SSC/HSSC results
    board = Column(String, nullable=True)
    specialization = Column(String, nullable=True)


class Experience(Base):
    """Professional roles / jobs held by the candidate."""
    __tablename__ = "experience"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, nullable=False)
    title = Column(String, nullable=True)
    organization = Column(String, nullable=True)
    start_date = Column(String, nullable=True)
    end_date = Column(String, nullable=True)
    emp_type = Column(String, nullable=True)     # full-time, part-time, research, etc.
    description = Column(Text, nullable=True)     # bullet points from the CV


class Publication(Base):
    """Both journal articles and conference papers — differentiated by pub_type."""
    __tablename__ = "publications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, nullable=False)
    pub_type = Column(String, nullable=True)     # "journal" or "conference"
    title = Column(Text, nullable=True)
    venue = Column(String, nullable=True)        # journal or conference name
    year = Column(String, nullable=True)
    authors_json = Column(Text, nullable=True)   # JSON array of author names


class Skill(Base):
    """One row per claimed skill. Flat list for simple querying."""
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, nullable=False)
    skill_name = Column(String, nullable=True)


class Patent(Base):
    """Patents filed or granted."""
    __tablename__ = "patents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, nullable=False)
    number = Column(String, nullable=True)
    title = Column(String, nullable=True)
    year = Column(String, nullable=True)


class Book(Base):
    """Books authored, co-authored, or edited by the candidate."""
    __tablename__ = "books"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, nullable=False)
    title = Column(String, nullable=True)
    publisher = Column(String, nullable=True)
    year = Column(String, nullable=True)
    role = Column(String, nullable=True)         # author, co-author, editor, etc.


class Project(Base):
    """Academic or professional projects listed on the CV."""
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, nullable=False)
    title = Column(String, nullable=True)
    organization = Column(String, nullable=True)
    start_date = Column(String, nullable=True)
    end_date = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    technologies = Column(String, nullable=True)  # comma-separated tech stack
    role = Column(String, nullable=True)


class AnalysisCache(Base):
    """
    Caches the JSON output of every analysis module so we don't
    re-invoke the LLM on every page load. Each row stores one
    module's result for one candidate.
    """
    __tablename__ = "analysis_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, nullable=False)
    module = Column(String, nullable=False)      # e.g. "education_profile"
    result_json = Column(Text, nullable=True)     # serialized analysis result
    computed_at = Column(String, nullable=True)   # ISO timestamp
