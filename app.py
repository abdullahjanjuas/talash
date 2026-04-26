# Streamlit Interface to run first as entry point

# Importing Libraries
import streamlit as st
import os
import json
import pandas as pd      

# Import all our other files
from database import create_tables
from parser import parse_cv
from llm_extractor import extract_cv_data
from db_operations import store_candidate, get_all_candidates_summary, get_candidate_detail,store_analysis_cache
from education_analyzer import analyze_education
from experience_analyzer import analyze_experience          # ← CHANGE 1: new import
from models import AnalysisCache
from database import SessionLocal
# Page confguration
st.set_page_config(
    page_title="TALASH",
    layout="wide"  
)

# Initialization
create_tables() # Only runs for safe side if tables do not exist already
os.makedirs("cvs", exist_ok=True)       # create /cvs folder if it doesn't exist
os.makedirs("outputs", exist_ok=True)   # create /outputs folder if it doesn't exist

# Header
st.title("TALASH: Smart HR Recruitment")
st.markdown("Automated CV Analysis System")
st.divider()  # horizontal line

# Sidebar Navigation
page = st.sidebar.radio(
    "Navigation",
    ["Upload CV", "All Candidates", "Candidate Detail", "Export Data"]
)

# PAGE 1: UPLOAD CV
if page == "Upload CV":
    st.header("Get your CV Processed!")
    st.info("Upload a PDF CV. The system extracts all data stores it in the database.")

    # File uploader Feature
    uploaded_file = st.file_uploader("Choose a PDF file", type=["pdf"])

    if uploaded_file is not None:
        # Shows file info so user knows it was received
        file_size_kb = uploaded_file.size / 1024
        st.write(f"**File:** {uploaded_file.name} ({file_size_kb:.1f} KB)")

        # Button to start processing
        if st.button("Click to process CV", type="primary"):
            # Loading sign
            with st.spinner("Step 1/4: Saving PDF to disk..."):
                pdf_path = f"cvs/{uploaded_file.name}"
                # uploaded_file.getbuffer() gives us the raw bytes of the file
                with open(pdf_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
            st.success(f"Step 1 done: saved to {pdf_path}")

            # STEP 2: Parse the PDF
            with st.spinner("Step 2/4: Extracting text from PDF..."):
                parse_result = parse_cv(pdf_path)
                cv_text = parse_result["text"]
                char_count = parse_result["char_count"]
                num_tables = len(parse_result["tables"])
            st.success(f"Step 2 done: extracted {char_count:,} characters, {num_tables} table(s) found")

            # Show extracted text in a collapsible section
            with st.expander("View raw extracted text (for debugging)"):
                # Only show first 3000 chars to avoid flooding the screen
                st.text(cv_text[:3000] + ("..." if len(cv_text) > 3000 else ""))

            # STEP 3: Send to LLM
            with st.spinner("Step 3/4: Our AI Agent is processing your CV.."):
                result = extract_cv_data(cv_text)

            # Check if LLM extraction succeeded
            if not result["success"]:
                # st.error() shows a red error box
                st.error(f" LLM extraction failed: {result['error']}")
                if result.get("raw"):
                    st.code(result["raw"])
                st.stop()

            extracted = result["data"]
            st.success("Step 3 done: Data Received!")

            # Show the raw JSON LLM returned
            with st.expander("View extracted JSON from LLM for debugging"):
                st.json(extracted)  # st.json() renders JSON with syntax highlighting

            # STEP 4: Store in database
            with st.spinner("Step 4/4: Storing in database..."):
                try:
                    candidate_id = store_candidate(extracted, uploaded_file.name)

                    # ── Education Profile Analysis ──
                    with st.spinner("Analyzing educational profile..."):
                        edu_analysis = analyze_education(candidate_id)
                        store_analysis_cache(candidate_id, "education_profile", edu_analysis)
                    st.success("Education Profile Analysis Completed!")

                    # ── Experience Profile Analysis ──           ← CHANGE 2A: new block
                    with st.spinner("Analyzing professional experience..."):
                        exp_analysis = analyze_experience(candidate_id)
                        store_analysis_cache(candidate_id, "experience_profile", exp_analysis)
                    st.success("Experience Profile Analysis Completed!")

                except Exception as e:
                    st.error(f"Database error: {str(e)}")
                    st.stop()

            st.success(f"Step 4 done: Stored as Candidate ID #{candidate_id}")
            st.balloons()  # fun visual effect for the demo

            # Extraction Summary
            st.divider()
            st.subheader("Extraction Summary")

            personal = extracted.get("personal", {})

            # st.columns() splits the row into equal-width columns
            col1, col2, col3, col4 = st.columns(4)
            # st.metric() shows a big number with a label — looks professional
            col1.metric("Education Records", len(extracted.get("education", [])))
            col2.metric("Experience Records", len(extracted.get("experience", [])))
            col3.metric("Publications", len(extracted.get("publications", [])))
            col4.metric("Skills Extracted", len(extracted.get("skills", [])))

            # Personal info row
            st.markdown(
                f"**Name:** {personal.get('name', '—')} &nbsp;|&nbsp; "
                f"**Email:** {personal.get('email', '—')} &nbsp;|&nbsp; "
                f"**Phone:** {personal.get('phone', '—')}"
            )

            # Education table
            if extracted.get("education"):
                st.subheader("Education")
                edu_df = pd.DataFrame(extracted["education"])
                st.dataframe(edu_df, use_container_width=True)

            # Experience table
            if extracted.get("experience"):
                st.subheader("Experience")
                exp_df = pd.DataFrame(extracted["experience"])
                st.dataframe(exp_df, use_container_width=True)

            # Publications table
            if extracted.get("publications"):
                st.subheader("Publications")
                pub_df = pd.DataFrame(extracted["publications"])
                # Convert authors list to string for display
                if "authors" in pub_df.columns:
                    pub_df["authors"] = pub_df["authors"].apply(
                        lambda x: ", ".join(x) if isinstance(x, list) else str(x)
                    )
                st.dataframe(pub_df, use_container_width=True)

            # Skills as tags
            if extracted.get("skills"):
                st.subheader("Skills")
                # Display skills in a grid — 5 per row
                skills = extracted["skills"]
                cols = st.columns(5)
                for i, skill in enumerate(skills):
                    cols[i % 5].markdown(f"• {skill}")


# PAGE 2: ALL CANDIDATES
# Shows every processed CV in one table
elif page == "All Candidates":
    st.header("All Candidates")

    # Fetch summary from database
    candidates = get_all_candidates_summary()

    if not candidates:
        st.warning("No candidates yet. Go to 'Upload CV' to add some.")
    else:
        st.info(f"**{len(candidates)}** candidate(s) in the database")

        # Convert list of dicts to pandas DataFrame for display
        df = pd.DataFrame(candidates)
        # hide_index=True removes the 0,1,2... row numbers on the left
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Quick stats row
        st.divider()
        st.subheader("Quick Stats")
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Candidates", len(candidates))
        col2.metric("With Publications",
                    sum(1 for c in candidates if c["Publications"] > 0))
        col3.metric("With CGPA",
                    sum(1 for c in candidates if c["CGPA"] not in ["—", None]))


# PAGE 3: CANDIDATE DETAIL
# Shows complete info for one selected candidate
elif page == "Candidate Detail":
    st.header("Candidate Detail")

    candidates = get_all_candidates_summary()
    if not candidates:
        st.warning("No candidates yet.")
    else:
        # Build a dict mapping ID: Name for the dropdown
        id_to_name = {c["ID"]: c["Name"] for c in candidates}

        # st.selectbox() creates a dropdown menu
        selected_id = st.selectbox(
            "Select a candidate",
            options=list(id_to_name.keys()),
            format_func=lambda x: f"#{x} — {id_to_name[x]}"
        )

        if selected_id:
            detail = get_candidate_detail(selected_id)
            c = detail["candidate"]

            st.subheader(f"👤 {c.name}")
            col1, col2 = st.columns(2)
            col1.markdown(f"**Email:** {c.email or '—'}")
            col1.markdown(f"**Phone:** {c.phone or '—'}")
            col2.markdown(f"**Address:** {c.address or '—'}")
            col2.markdown(f"**CV File:** {c.cv_filename or '—'}")

            # ← CHANGE 2B: tab count expanded from 7 to 8
            tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(
                ["Education", "Experience", "Projects", "Publications",
                 "Skills", "Patents & Books", "Educational Analysis", "Experience Analysis"]
            )

            with tab1:
                if detail["education"]:
                    for edu in detail["education"]:
                        st.markdown(f"**{edu.degree}** — {edu.institution}")
                        st.markdown(
                            f"Level: {edu.level or '—'} &nbsp;|&nbsp; "
                            f"{edu.start_year or '?'} – {edu.end_year or 'present'} &nbsp;|&nbsp; "
                            f"CGPA: {edu.cgpa or '—'}"
                        )
                        st.divider()
                else:
                    st.info("No education records found in this CV.")

            with tab2:
                if detail["experience"]:
                    for exp in detail["experience"]:
                        st.markdown(f"**{exp.title}** — {exp.organization}")
                        st.markdown(
                            f"{exp.start_date or 'Date not specified'} – {exp.end_date or 'Date not specified'} &nbsp;|&nbsp; "
                            f"Type: {exp.emp_type or '—'}"
                        )
                        if exp.description:
                            st.markdown(exp.description)
                        st.divider()
                else:
                    st.info("No experience records found.")

            with tab3:
                if detail["projects"]:
                    for proj in detail["projects"]:
                        st.markdown(f"**{proj.title}**")
                        if proj.organization:
                            st.markdown(f"*{proj.organization}*")
                        date_str = f"{proj.start_date or 'Date not specified'} – {proj.end_date or 'Date not specified'}"
                        meta_parts = [date_str]
                        if proj.role:
                            meta_parts.append(f"Role: {proj.role}")
                        if proj.technologies:
                            meta_parts.append(f"Tech: {proj.technologies}")
                        st.markdown(" &nbsp;|&nbsp; ".join(meta_parts))
                        if proj.description:
                            st.markdown(proj.description)
                        st.divider()
                else:
                    st.info("No projects found in this CV.")
            
            with tab4:
                if detail["publications"]:
                    for i, pub in enumerate(detail["publications"], 1):
                        st.markdown(f"**{i}. {pub.title}**")
                        # Parse authors back from JSON string to list
                        authors = json.loads(pub.authors_json) if pub.authors_json else []
                        st.markdown(
                            f"*{pub.venue or '—'}* &nbsp;|&nbsp; "
                            f"Year: {pub.year or '—'} &nbsp;|&nbsp; "
                            f"Type: {pub.pub_type or '—'}"
                        )
                        if authors:
                            st.markdown(f"Authors: {', '.join(authors)}")
                        st.divider()
                else:
                    st.info("No publications found.")

            with tab5:
                if detail["skills"]:
                    skills_list = [s.skill_name for s in detail["skills"]]
                    cols = st.columns(3)
                    for i, skill in enumerate(skills_list):
                        cols[i % 3].markdown(f"• {skill}")
                else:
                    st.info("No skills found.")

            with tab6:
                if detail["patents"]:
                    st.markdown("**Patents**")
                    for p in detail["patents"]:
                        st.markdown(f"• {p.title} ({p.number or '—'}) — {p.year or '—'}")
                if detail["books"]:
                    st.markdown("**Books**")
                    for b in detail["books"]:
                        st.markdown(f"• *{b.title}* — {b.publisher or '—'} ({b.year or '—'}) — Role: {b.role or '—'}")
                if not detail["patents"] and not detail["books"]:
                    st.info("No patents or books found.")
                    
            with tab7:
                st.subheader("🎓 Education Profile Analysis")
                
                db = SessionLocal()
                analysis = db.query(AnalysisCache).filter(
                    AnalysisCache.candidate_id == selected_id,
                    AnalysisCache.module == "education_profile"
                ).first()

                if analysis:
                    res = json.loads(analysis.result_json)

                    col1, col2, col3 = st.columns(3)

                    col1.metric("University Score", round(res["avg_university_score"], 2))
                    col2.metric("Academic Score", round(res["avg_academic_score"], 2) if res["avg_academic_score"] else "—")
                    col3.metric("UG / PG / PhD", f"{res['ug_count']} / {res['pg_count']} / {res['phd_count']}")

                    st.divider()

                    st.write("📈 Progression:", res["progression"])
                    st.write("⏳ Gaps:", res["gaps"])
                    st.write("✔ Justified Gaps:", res["justified_gaps"])
                    st.write("🧠 Final Interpretation:", res["interpretation"])

                else:
                    st.info("No education analysis available yet.")
                db.close()

            # ← CHANGE 2C: New tab8 block — Experience Analysis
            with tab8:
                st.subheader("💼 Experience Profile Analysis")

                db = SessionLocal()
                exp_analysis_record = db.query(AnalysisCache).filter(
                    AnalysisCache.candidate_id == selected_id,
                    AnalysisCache.module == "experience_profile"
                ).first()
                db.close()

                if not exp_analysis_record:
                    st.info("No experience analysis available. Re-upload the CV to generate it.")
                else:
                    res = json.loads(exp_analysis_record.result_json)

                    if not res.get("has_data"):
                        st.warning("No experience records found for this candidate.")
                    else:
                        # ── Top-level score metrics row ──
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("Final Score",   round(res["final_score"], 2))
                        col2.metric("Continuity",    round(res["continuity_score"], 2))
                        col3.metric("Progression",   round(res["progression_score"], 2))
                        col4.metric("Consistency",   round(res["consistency_score"], 2))

                        st.divider()
                        st.write("🧠 **Interpretation:**", res["interpretation"])
                        st.write("📈 **Career Trajectory:**", res["trajectory"].capitalize())
                        st.write(
                            f"📋 Total Roles: **{res['total_roles']}** | "
                            f"Unexplained Gaps: **{res['unexplained_gaps_count']}** | "
                            f"Suspicious Overlaps: **{res['suspicious_overlaps_count']}**"
                        )

                        st.divider()

                        # ── Career Progression Table ──
                        st.subheader("Career Progression")
                        prog = res.get("progression", {})
                        roles = prog.get("roles_analyzed", [])
                        if roles:
                            prog_df = pd.DataFrame([{
                                "Title":        r["title"],
                                "Organization": r["organization"],
                                "Start":        r["start_date"],
                                "Seniority":    r["tier_label"],
                                "Tier #":       r["tier"]
                            } for r in roles])
                            st.dataframe(prog_df, use_container_width=True, hide_index=True)
                        else:
                            st.info("No role data available for progression chart.")

                        st.divider()

                        # ── Professional Gaps ──
                        st.subheader("Professional Gaps")
                        gaps = res.get("gaps", [])
                        if gaps:
                            for g in gaps:
                                status_icon = "✅" if g["justified"] else "⚠️"
                                label = "Entry gap" if g["type"] == "entry_gap" else "Between-jobs gap"
                                st.markdown(
                                    f"{status_icon} **{label}** — {g['description']}  \n"
                                    f"*{g['justification']}*"
                                )
                        else:
                            st.success("No significant professional gaps detected.")

                        st.divider()

                        # ── Experience–Experience Overlaps ──
                        st.subheader("Experience Overlaps")
                        overlaps = res.get("exp_overlaps", [])
                        if overlaps:
                            for o in overlaps:
                                icon = "🔴" if o["suspicion"] == "high" else "🟡"
                                st.markdown(
                                    f"{icon} **{o['job_a']}** @ {o['org_a']}  ↔  "
                                    f"**{o['job_b']}** @ {o['org_b']}  \n"
                                    f"Duration: ~{o['duration_months']} months | {o['note']}"
                                )
                        else:
                            st.success("No overlapping experience records detected.")

                        # ── Education–Experience Overlaps ──
                        edu_overlaps = res.get("edu_exp_overlaps", [])
                        if edu_overlaps:
                            st.subheader("Education–Work Overlaps")
                            for o in edu_overlaps:
                                st.markdown(
                                    f"📚 **{o['degree']}** @ {o['institution']}  ↔  "
                                    f"**{o['job']}** @ {o['organization']} ({o['emp_type']})  \n"
                                    f"*{o['assessment']}*"
                                )

                        st.divider()

                        # ── Missing Info + Email Draft ──
                        missing = res.get("missing_info", {})
                        missing_fields = missing.get("missing_fields", [])
                        email_draft    = missing.get("email_draft")

                        st.subheader("Data Completeness")
                        st.metric("Completeness Score", round(missing.get("completeness_score", 1.0), 2))

                        if missing_fields:
                            st.warning("The following fields are missing from experience records:")
                            for field in missing_fields:
                                st.markdown(f"  • {field}")

                        if email_draft:
                            st.subheader("📧 Auto-Generated Follow-Up Email")
                            st.info("Copy and send this email to request missing details from the candidate.")
                            st.text_area(
                                label="Email Draft",
                                value=email_draft,
                                height=350,
                                label_visibility="collapsed"
                            )
                        else:
                            st.success("All critical fields are complete — no follow-up needed.")


# PAGE 4: EXPORT DATA
# Download all candidate data as CSV or Excel
elif page == "Export Data":
    st.header("Export Candidate Data")

    candidates = get_all_candidates_summary()
    if not candidates:
        st.warning("No data to export yet.")
    else:
        df = pd.DataFrame(candidates)

        col1, col2 = st.columns(2)

        with col1:
            # Convert DataFrame to CSV bytes
            csv_bytes = df.to_csv(index=False).encode("utf-8")
            # st.download_button() creates a button that downloads a file
            st.download_button(
                label="Download as CSV",
                data=csv_bytes,
                file_name="talash_candidates.csv",
                mime="text/csv"
            )

        with col2:
            # Write Excel to disk first, then read it for download
            excel_path = "outputs/talash_candidates.xlsx"
            df.to_excel(excel_path, index=False)
            with open(excel_path, "rb") as f:
                st.download_button(
                    label="Download as Excel",
                    data=f,
                    file_name="talash_candidates.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

        st.divider()
        st.subheader("Data Preview")
        st.dataframe(df, use_container_width=True, hide_index=True)