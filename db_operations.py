# This file handles all database reads and writes.
# It takes the Python dict from llama and stores it across multiple tables.

import json
from datetime import datetime
from database import SessionLocal  
from models import (                 # importing all tables
    Candidate, Education, Experience,
    Publication, Skill, Patent, Book, Project, AnalysisCache
)

def store_analysis_cache(candidate_id: int, module: str, result: dict):
    db = SessionLocal()
    try:
        # ADD THIS BLOCK RIGHT HERE
        existing = db.query(AnalysisCache).filter(
            AnalysisCache.candidate_id == candidate_id,
            AnalysisCache.module == module
        ).first()

        if existing:
            # UPDATE existing record
            existing.result_json = json.dumps(result)
            existing.computed_at = str(datetime.now())
        else:
            # INSERT new record
            db.add(AnalysisCache(
                candidate_id=candidate_id,
                module=module,
                result_json=json.dumps(result),
                computed_at=str(datetime.now())
            ))

        db.commit()

    except:
        db.rollback()
        raise
    finally:
        db.close()
        
def store_candidate(extracted_data: dict, cv_filename: str) -> int:
    """
    Insert a complete extracted CV into the database.
    
    extracted_data: the dict returned by llm_extractor.py
    cv_filename: original PDF filename, stored for reference
    
    Returns the new candidate's ID.
    Raises an exception if anything goes wrong, the caller handles it.
    """
    # Open a database session
    db = SessionLocal()

    try:
        personal = extracted_data.get("personal", {})

        # Insert the main candidate row
        candidate = Candidate(
            name=personal.get("name", "Unknown"),
            email=personal.get("email"),
            phone=personal.get("phone"),
            address=personal.get("address"),
            cv_filename=cv_filename
        )
        db.add(candidate)

        # db.flush() sends the INSERT to the DB without committing.
        # This is needed to get the auto-generated candidate.id
        # so we can use it as the foreign key in all other tables.
        db.flush()
        cid = candidate.id  # this is the foreign key for all related tables

        # Insert education records
        # extracted_data["education"] is a list: one item per degree
        # Insert education records
        for edu in extracted_data.get("education", []):
            if not edu:
                continue
            
            # Safely parse cgpa — some LLMs return strings like "3.5/4.0"
            raw_cgpa = edu.get("cgpa")
            parsed_cgpa = None
            if raw_cgpa is not None:
                try:
                    parsed_cgpa = float(str(raw_cgpa).split("/")[0])
                except:
                    parsed_cgpa = None

            raw_pct = edu.get("percentage")
            parsed_pct = None
            if raw_pct is not None:
                try:
                    parsed_pct = float(str(raw_pct).replace("%", "").strip())
                except:
                    parsed_pct = None

            db.add(Education(
                candidate_id=cid,
                level=edu.get("level"),
                degree=edu.get("degree"),
                institution=edu.get("institution"),
                cgpa=parsed_cgpa,
                percentage=parsed_pct,
                board=edu.get("board"),
                specialization=edu.get("specialization"),
                start_year=str(edu.get("start_year", "")),
                end_year=str(edu.get("end_year", ""))
            ))

        # Insert experience records
        for exp in extracted_data.get("experience", []):
            if not exp:
                continue
            db.add(Experience(
                candidate_id=cid,
                title=exp.get("title"),
                organization=exp.get("organization"),
                start_date=exp.get("start_date"),
                end_date=exp.get("end_date"),
                emp_type=exp.get("type"),
                description=exp.get("description")
            ))

        # Insert publications
        for pub in extracted_data.get("publications", []):
            if not pub:
                continue
            # authors is a list
            # We convert it to a JSON string to store in a single TEXT column
            authors_list = pub.get("authors", [])
            db.add(Publication(
                candidate_id=cid,
                pub_type=pub.get("type"),
                title=pub.get("title"),
                venue=pub.get("venue"),
                year=str(pub.get("year", "")),
                authors_json=json.dumps(authors_list)  # list → JSON string
            ))

        # Insert skills
        # skills is a flat list of strings
        # We create one row per skill for easy querying later
        for skill in extracted_data.get("skills", []):
            if skill:
                db.add(Skill(
                    candidate_id=cid,
                    skill_name=str(skill)
                ))

        # Insert patents
        for patent in extracted_data.get("patents", []):
            if not patent:
                continue
            db.add(Patent(
                candidate_id=cid,
                number=patent.get("number"),
                title=patent.get("title"),
                year=str(patent.get("year", ""))
            ))

        # Insert books
        for book in extracted_data.get("books", []):
            if not book:
                continue
            db.add(Book(
                candidate_id=cid,
                title=book.get("title"),
                publisher=book.get("publisher"),
                year=str(book.get("year", "")),
                role=book.get("role")
            ))

        # Insert projects
        for project in extracted_data.get("projects", []):
            if not project:
                continue
            db.add(Project(
                candidate_id=cid,
                title=project.get("title"),
                organization=project.get("organization"),
                start_date=project.get("start_date"),
                end_date=project.get("end_date"),
                description=project.get("description"),
                technologies=project.get("technologies"),
                role=project.get("role")
            ))

        # db.commit()

        # db.commit() permanently saves everything to talash.db
        # If commit fails, we rollback in the except block
        db.commit()
        return cid  # return the new candidate's ID

    except Exception as e:
        db.rollback()  # undo everything if anything failed
        raise e        # re-raise so app.py can show the error

    finally:
        db.close()     # always close the session, even if an error occurred


def get_all_candidates_summary() -> list:
    """
    Fetch a summary of all candidates for the main candidates table in the UI.
    Returns a list of dicts, one per candidate.
    """
    db = SessionLocal()
    try:
        # Query the candidates table
        candidates = db.query(Candidate).all()
        result = []

        for c in candidates:
            # For each candidate, count their related records
            edu_list = db.query(Education).filter(
                Education.candidate_id == c.id
            ).all()

            exp_count = db.query(Experience).filter(
                Experience.candidate_id == c.id
            ).count()

            pub_count = db.query(Publication).filter(
                Publication.candidate_id == c.id
            ).count()

            skills = db.query(Skill).filter(
                Skill.candidate_id == c.id
            ).all()

            # Get the last education record as highest degree
            highest = edu_list[-1] if edu_list else None

            result.append({
                "ID": c.id,
                "Name": c.name or "—",
                "Email": c.email or "—",
                "Highest Degree": highest.degree if highest else "—",
                "Institution": highest.institution if highest else "—",
                "CGPA": highest.cgpa if highest else "—",
                "Education Records": len(edu_list),
                "Experience": exp_count,
                "Publications": pub_count,
                "Skills": ", ".join([s.skill_name for s in skills[:4]])
            })

        return result
    finally:
        db.close()


def get_candidate_detail(candidate_id: int) -> dict:
    """
    Fetch complete data for one candidate: all tables, all records.
    Used in the Candidate Detail page of the UI.
    """
    db = SessionLocal()
    try:
        # .first() returns one object or None (not a list)
        c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not c:
            return {}

        return {
            "candidate": c,
            "education": db.query(Education).filter(
                Education.candidate_id == candidate_id).all(),
            "experience": db.query(Experience).filter(
                Experience.candidate_id == candidate_id).all(),
            "publications": db.query(Publication).filter(
                Publication.candidate_id == candidate_id).all(),
            "skills": db.query(Skill).filter(
                Skill.candidate_id == candidate_id).all(),
            "patents": db.query(Patent).filter(
                Patent.candidate_id == candidate_id).all(),
            "books": db.query(Book).filter(
                Book.candidate_id == candidate_id).all(),
            "projects": db.query(Project).filter(
                Project.candidate_id == candidate_id).all(),
        }
    finally:
        db.close()