# This file determines the schema and tables in database

from sqlalchemy import Column, Integer, String, Float, Text
from sqlalchemy.orm import declarative_base

# Base is the parent class all our table classes inherit from.
# SQLAlchemy uses it to track all our tables.
Base = declarative_base()


class Candidate(Base):
    # This becomes the candidates table in talash.db
    __tablename__ = "candidates"

    # Integer primary key — auto-increments (1, 2, 3...) for each new candidate
    id = Column(Integer, primary_key=True, autoincrement=True)

    # nullable=True means the column can be empty — important because
    # some CVs won't have all fields and we don't want the insert to fail
    name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    address = Column(String, nullable=True)
    cv_filename = Column(String, nullable=True)  # which PDF file this came from


class Education(Base):
    __tablename__ = "education"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # candidate_id links this row back to the candidates table.
    # One candidate can have MANY education records
    candidate_id = Column(Integer, nullable=False)

    level = Column(String, nullable=True)        # e.g. "Bachelors", "PhD"
    degree = Column(String, nullable=True)       # e.g. "BSc Computer Science"
    institution = Column(String, nullable=True)  # e.g. "NUST"
    cgpa = Column(Float, nullable=True)          # Float because 3.85 is not an integer
    start_year = Column(String, nullable=True)   # String not Integer — some CVs write "2018-2019"
    end_year = Column(String, nullable=True)
    # SSC/HSSC Results
    percentage = Column(Float, nullable=True)
    board = Column(String, nullable=True)
    specialization = Column(String, nullable=True)


class Experience(Base):
    __tablename__ = "experience"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, nullable=False)
    title = Column(String, nullable=True)         # e.g. "Research Associate"
    organization = Column(String, nullable=True)  # e.g. "LUMS"
    start_date = Column(String, nullable=True)
    end_date = Column(String, nullable=True)
    emp_type = Column(String, nullable=True)      # "full-time", "part-time", "research"
    description = Column(Text, nullable=True)     # full role description / bullet points


class Publication(Base):
    __tablename__ = "publications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, nullable=False)
    pub_type = Column(String, nullable=True)      # "journal" or "conference"
    title = Column(Text, nullable=True)           # Text not String — titles can be very long
    venue = Column(String, nullable=True)         # journal name or conference name
    year = Column(String, nullable=True)
    # Authors is a list but SQL can't store lists directly.
    authors_json = Column(Text, nullable=True)


class Skill(Base):
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, nullable=False)
    skill_name = Column(String, nullable=True)    # one row per skill


class Patent(Base):
    __tablename__ = "patents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, nullable=False)
    number = Column(String, nullable=True)
    title = Column(String, nullable=True)
    year = Column(String, nullable=True)


class Book(Base):
    __tablename__ = "books"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, nullable=False)
    title = Column(String, nullable=True)
    publisher = Column(String, nullable=True)
    year = Column(String, nullable=True)
    role = Column(String, nullable=True)        

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, nullable=False)
    title = Column(String, nullable=True)
    organization = Column(String, nullable=True)   # university, company, or personal
    start_date = Column(String, nullable=True)
    end_date = Column(String, nullable=True)
    description = Column(Text, nullable=True)      # full description / bullet points
    technologies = Column(String, nullable=True)   # comma-separated tech stack
    role = Column(String, nullable=True)           # "Lead", "Team Member", etc.

class AnalysisCache(Base):
    # This table stores LLM's analysis results so we don't re-call the API
    __tablename__ = "analysis_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, nullable=False)
    module = Column(String, nullable=False)      
    result_json = Column(Text, nullable=True)    
    computed_at = Column(String, nullable=True)  