# app.py — TALASH: Smart HR Recruitment System
# Entry point.  Run with:  streamlit run app.py
#
# PAGE STRUCTURE:
#   1. Upload CV          — parse, extract, store, run all analysis modules
#   2. All Candidates     — summary table + quick charts
#   3. Candidate Detail   — tabbed deep-dive per candidate
#        Tab 1: Education        Tab 2: Experience    Tab 3: Projects
#        Tab 4: Publications     Tab 5: Skills        Tab 6: Patents & Books
#        Tab 7: Edu Analysis     Tab 8: Exp Analysis  Tab 9: Conference Analysis
#        Tab 10: Journal Analysis Tab 11: Topic/Coauthor  Tab 12: Supervision/Books/Patents
#        Tab 13: Skill Analysis
#   4. Rankings Dashboard  — comparative ranked view with charts
#   5. Export Data         — CSV / Excel download

import streamlit as st
import os
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from database import create_tables, SessionLocal
from parser import parse_cv
from llm_extractor import extract_cv_data
from db_operations import (
    store_candidate, get_all_candidates_summary,
    get_candidate_detail, store_analysis_cache
)
from models import AnalysisCache, Candidate

# Analysis modules
from education_analyzer import analyze_education
from experience_analyzer import analyze_experience
from conference_analyzer import analyze_conference_papers
from journal_analyzer import analyze_journal_papers
from topic_coauthor_analyzer import analyze_topics_and_coauthors
from supervision_analyzer import analyze_supervision_books_patents
from skill_analyzer import analyze_skills
from candidate_ranker import rank_all_candidates, generate_candidate_summary, compute_candidate_score

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="TALASH", layout="wide", page_icon="🔍")

# ── Init ──────────────────────────────────────────────────────────────────────
create_tables()
os.makedirs("cvs", exist_ok=True)
os.makedirs("outputs", exist_ok=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.image("https://img.icons8.com/color/96/000000/resume.png", width=60)
st.sidebar.title("TALASH")
st.sidebar.markdown("*Smart HR Recruitment System*")
st.sidebar.divider()

page = st.sidebar.radio(
    "Navigation",
    ["Upload CV", "All Candidates", "Candidate Detail", "Rankings Dashboard", "Export Data"]
)


# =============================================================================
# HELPER: run all analysis modules for a candidate
# =============================================================================
def run_all_analyses(candidate_id: int):
    """Run every analysis module and cache results. Returns dict of results."""
    results = {}

    with st.spinner("Analyzing educational profile..."):
        r = analyze_education(candidate_id)
        store_analysis_cache(candidate_id, "education_profile", r)
        results["education_profile"] = r
    st.success("✅ Education analysis complete")

    with st.spinner("Analyzing professional experience..."):
        r = analyze_experience(candidate_id)
        store_analysis_cache(candidate_id, "experience_profile", r)
        results["experience_profile"] = r
    st.success("✅ Experience analysis complete")

    with st.spinner("Analyzing conference publications..."):
        r = analyze_conference_papers(candidate_id)
        store_analysis_cache(candidate_id, "conference_profile", r)
        results["conference_profile"] = r
    st.success("✅ Conference analysis complete")

    with st.spinner("Analyzing journal publications..."):
        r = analyze_journal_papers(candidate_id)
        store_analysis_cache(candidate_id, "journal_profile", r)
        results["journal_profile"] = r
    st.success("✅ Journal analysis complete")

    with st.spinner("Analyzing research topics and co-authors..."):
        r = analyze_topics_and_coauthors(candidate_id)
        store_analysis_cache(candidate_id, "topic_coauthor_profile", r)
        results["topic_coauthor_profile"] = r
    st.success("✅ Topic & co-author analysis complete")

    with st.spinner("Analyzing supervision, books, and patents..."):
        r = analyze_supervision_books_patents(candidate_id)
        store_analysis_cache(candidate_id, "supervision_books_patents", r)
        results["supervision_books_patents"] = r
    st.success("✅ Supervision/books/patents analysis complete")

    with st.spinner("Analyzing skill alignment..."):
        r = analyze_skills(candidate_id)
        store_analysis_cache(candidate_id, "skill_profile", r)
        results["skill_profile"] = r
    st.success("✅ Skill analysis complete")

    return results


def _load_cache(candidate_id: int, module: str):
    """Load a single analysis result from cache. Returns dict or None."""
    db = SessionLocal()
    try:
        rec = db.query(AnalysisCache).filter(
            AnalysisCache.candidate_id == candidate_id,
            AnalysisCache.module == module
        ).first()
        return json.loads(rec.result_json) if rec else None
    finally:
        db.close()


# =============================================================================
# PAGE 1: UPLOAD CV
# =============================================================================
if page == "Upload CV":
    st.title("🔍 TALASH: Upload & Process CV")
    st.info("Upload a PDF CV. The system will extract all data and run the full analysis pipeline.")

    uploaded_file = st.file_uploader("Choose a PDF file", type=["pdf"])

    if uploaded_file:
        st.write(f"**File:** {uploaded_file.name} ({uploaded_file.size/1024:.1f} KB)")

        if st.button("Process CV", type="primary"):

            # Step 1: Save PDF
            with st.spinner("Step 1/4: Saving PDF..."):
                pdf_path = f"cvs/{uploaded_file.name}"
                with open(pdf_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
            st.success(f"Step 1 done: saved to {pdf_path}")

            # Step 2: Parse
            with st.spinner("Step 2/4: Extracting text from PDF..."):
                parse_result = parse_cv(pdf_path)
                cv_text      = parse_result["text"]
            st.success(f"Step 2 done: {parse_result['char_count']:,} chars, "
                       f"{len(parse_result['tables'])} table(s)")

            with st.expander("View extracted text (debug)"):
                st.text(cv_text[:3000] + ("..." if len(cv_text) > 3000 else ""))

            # Step 3: LLM extraction
            with st.spinner("Step 3/4: AI extracting structured data..."):
                result = extract_cv_data(cv_text)

            if not result["success"]:
                st.error(f"LLM extraction failed: {result['error']}")
                st.stop()

            extracted = result["data"]
            st.success("Step 3 done: structured data extracted")

            with st.expander("View extracted JSON (debug)"):
                st.json(extracted)

            # Step 4: Store + Analyze
            with st.spinner("Step 4/4: Storing in database..."):
                try:
                    candidate_id = store_candidate(extracted, uploaded_file.name)
                except Exception as e:
                    st.error(f"Database error: {str(e)}")
                    st.stop()

            st.success(f"Stored as Candidate #{candidate_id}")

            # Run all analyses
            st.divider()
            st.subheader("Running Full Analysis Pipeline...")
            run_all_analyses(candidate_id)

            st.balloons()
            st.divider()

            # Extraction summary
            st.subheader("Extraction Summary")
            personal = extracted.get("personal", {})
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Education Records",   len(extracted.get("education", [])))
            col2.metric("Experience Records",  len(extracted.get("experience", [])))
            col3.metric("Publications",        len(extracted.get("publications", [])))
            col4.metric("Skills",              len(extracted.get("skills", [])))

            st.markdown(
                f"**Name:** {personal.get('name','—')} &nbsp;|&nbsp; "
                f"**Email:** {personal.get('email','—')} &nbsp;|&nbsp; "
                f"**Phone:** {personal.get('phone','—')}"
            )

            # Show tables
            if extracted.get("education"):
                st.subheader("Education")
                st.dataframe(pd.DataFrame(extracted["education"]), use_container_width=True)

            if extracted.get("experience"):
                st.subheader("Experience")
                st.dataframe(pd.DataFrame(extracted["experience"]), use_container_width=True)

            if extracted.get("publications"):
                st.subheader("Publications")
                pub_df = pd.DataFrame(extracted["publications"])
                if "authors" in pub_df.columns:
                    pub_df["authors"] = pub_df["authors"].apply(
                        lambda x: ", ".join(x) if isinstance(x, list) else str(x))
                st.dataframe(pub_df, use_container_width=True)

            if extracted.get("skills"):
                st.subheader("Skills")
                cols = st.columns(5)
                for i, sk in enumerate(extracted["skills"]):
                    cols[i % 5].markdown(f"• {sk}")

            # Show quick score
            st.divider()
            score_data = compute_candidate_score(candidate_id)
            st.subheader(f"Overall Score: **{score_data['total_score_pct']}%**")
            sub = score_data["sub_scores"]
            score_df = pd.DataFrame({
                "Module":  list(sub.keys()),
                "Score":   [round(v * 100, 1) for v in sub.values()]
            })
            fig = px.bar(score_df, x="Module", y="Score", text="Score",
                         color="Module", range_y=[0, 100],
                         color_discrete_sequence=px.colors.qualitative.Set2)
            fig.update_layout(showlegend=False, margin=dict(t=20, b=20), height=300)
            fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            st.plotly_chart(fig, use_container_width=True)


# =============================================================================
# PAGE 2: ALL CANDIDATES
# =============================================================================
elif page == "All Candidates":
    st.title("👥 All Candidates")

    candidates = get_all_candidates_summary()

    if not candidates:
        st.warning("No candidates yet. Go to 'Upload CV' to add some.")
    else:
        st.info(f"**{len(candidates)}** candidate(s) in the database")

        df = pd.DataFrame(candidates)
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("Quick Stats")
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Candidates", len(candidates))
        c2.metric("With Publications",
                  sum(1 for c in candidates if c["Publications"] > 0))
        c3.metric("With CGPA",
                  sum(1 for c in candidates if c["CGPA"] not in ["—", None]))

        st.divider()
        st.subheader("Charts")
        ch1, ch2 = st.columns(2)

        with ch1:
            st.markdown("**Publications per Candidate**")
            pub_df = pd.DataFrame({
                "Candidate": [c["Name"] or f"#{c['ID']}" for c in candidates],
                "Publications": [c["Publications"] for c in candidates]
            })
            fig = px.bar(pub_df, x="Candidate", y="Publications", text="Publications",
                         color_discrete_sequence=["#4C8BF5"])
            fig.update_layout(margin=dict(t=20, b=40), height=300)
            fig.update_traces(textposition="outside")
            st.plotly_chart(fig, use_container_width=True)

        with ch2:
            st.markdown("**CGPA Distribution**")
            cgpa_vals = [c for c in candidates if c["CGPA"] not in ["—", None]]
            if cgpa_vals:
                cgpa_df = pd.DataFrame({
                    "Candidate": [c["Name"] or f"#{c['ID']}" for c in cgpa_vals],
                    "CGPA": [c["CGPA"] for c in cgpa_vals]
                })
                fig = px.bar(cgpa_df, x="Candidate", y="CGPA", text="CGPA",
                             color_discrete_sequence=["#34A853"], range_y=[0, 4.5])
                fig.update_layout(margin=dict(t=20, b=40), height=300)
                fig.update_traces(texttemplate="%{text:.2f}", textposition="outside")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No CGPA data available.")


# =============================================================================
# PAGE 3: CANDIDATE DETAIL
# =============================================================================
elif page == "Candidate Detail":
    st.title("📋 Candidate Detail")

    candidates = get_all_candidates_summary()
    if not candidates:
        st.warning("No candidates yet.")
    else:
        id_to_name  = {c["ID"]: c["Name"] for c in candidates}
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

            # Score badge
            score_data = compute_candidate_score(selected_id)
            pct = score_data["total_score_pct"]
            color = "#2ecc71" if pct >= 75 else "#f39c12" if pct >= 55 else "#e74c3c"
            st.markdown(
                f"<div style='background:{color};padding:8px 16px;border-radius:8px;"
                f"display:inline-block;color:white;font-weight:bold;margin-bottom:12px'>"
                f"Overall Score: {pct}%</div>",
                unsafe_allow_html=True
            )

            # Re-run option
            if st.button("🔄 Re-run All Analyses"):
                run_all_analyses(selected_id)
                st.rerun()

            st.divider()

            # --- 13 Tabs ---
            (tab1, tab2, tab3, tab4, tab5, tab6,
             tab7, tab8, tab9, tab10, tab11, tab12, tab13) = st.tabs([
                "Education", "Experience", "Projects", "Publications",
                "Skills", "Patents & Books",
                "📊 Edu Analysis", "💼 Exp Analysis", "🎤 Conference",
                "📰 Journals", "🔬 Topics/Coauthors", "🎓 Supervision",
                "🛠️ Skill Analysis"
            ])

            # TAB 1: Education
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
                    st.info("No education records.")

            # TAB 2: Experience
            with tab2:
                if detail["experience"]:
                    for exp in detail["experience"]:
                        st.markdown(f"**{exp.title}** — {exp.organization}")
                        st.markdown(
                            f"{exp.start_date or '?'} – {exp.end_date or '?'} "
                            f"&nbsp;|&nbsp; Type: {exp.emp_type or '—'}"
                        )
                        if exp.description:
                            st.markdown(exp.description)
                        st.divider()
                else:
                    st.info("No experience records.")

            # TAB 3: Projects
            with tab3:
                if detail["projects"]:
                    for proj in detail["projects"]:
                        st.markdown(f"**{proj.title}**")
                        if proj.organization:
                            st.markdown(f"*{proj.organization}*")
                        meta = [f"{proj.start_date or '?'} – {proj.end_date or '?'}"]
                        if proj.role: meta.append(f"Role: {proj.role}")
                        if proj.technologies: meta.append(f"Tech: {proj.technologies}")
                        st.markdown(" &nbsp;|&nbsp; ".join(meta))
                        if proj.description:
                            st.markdown(proj.description)
                        st.divider()
                else:
                    st.info("No projects.")

            # TAB 4: Publications
            with tab4:
                if detail["publications"]:
                    for i, pub in enumerate(detail["publications"], 1):
                        authors = json.loads(pub.authors_json) if pub.authors_json else []
                        st.markdown(f"**{i}. {pub.title}**")
                        st.markdown(
                            f"*{pub.venue or '—'}* &nbsp;|&nbsp; "
                            f"Year: {pub.year or '—'} &nbsp;|&nbsp; Type: {pub.pub_type or '—'}"
                        )
                        if authors:
                            st.markdown(f"Authors: {', '.join(authors)}")
                        st.divider()
                else:
                    st.info("No publications.")

            # TAB 5: Skills
            with tab5:
                if detail["skills"]:
                    cols = st.columns(3)
                    for i, sk in enumerate(detail["skills"]):
                        cols[i % 3].markdown(f"• {sk.skill_name}")
                else:
                    st.info("No skills.")

            # TAB 6: Patents & Books
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
                    st.info("No patents or books.")

            # TAB 7: Education Analysis
            with tab7:
                st.subheader("🎓 Education Profile Analysis")
                res = _load_cache(selected_id, "education_profile")
                if res:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("University Score",  round(res["avg_university_score"], 2))
                    c2.metric("Academic Score",    round(res["avg_academic_score"], 2) if res["avg_academic_score"] else "—")
                    c3.metric("UG / PG / PhD",     f"{res['ug_count']} / {res['pg_count']} / {res['phd_count']}")

                    score_df = pd.DataFrame({
                        "Metric": ["University Score", "Academic Score"],
                        "Score":  [res["avg_university_score"] or 0, res["avg_academic_score"] or 0]
                    })
                    fig = px.bar(score_df, x="Metric", y="Score", text="Score",
                                 color="Metric", range_y=[0, 1],
                                 color_discrete_sequence=["#4C8BF5", "#FBBC04"])
                    fig.update_layout(showlegend=False, height=280, margin=dict(t=20, b=20))
                    fig.update_traces(texttemplate="%{text:.2f}", textposition="outside")
                    st.plotly_chart(fig, use_container_width=True)

                    st.write("📈 Progression:", res["progression"])
                    st.write("⏳ Gaps:", res["gaps"])
                    st.write("✔ Justified Gaps:", res["justified_gaps"])
                    st.write("🧠 Interpretation:", res["interpretation"])
                    st.write(f"**Final Score:** {res.get('final_score', '—')}")
                else:
                    st.info("No education analysis cached. Upload or re-run.")

            # TAB 8: Experience Analysis
            with tab8:
                st.subheader("💼 Experience Profile Analysis")
                res = _load_cache(selected_id, "experience_profile")
                if not res:
                    st.info("No experience analysis cached.")
                elif not res.get("has_data"):
                    st.warning(res.get("message", "No experience data."))
                else:
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Final Score",    round(res["final_score"], 2))
                    c2.metric("Continuity",     round(res["continuity_score"], 2))
                    c3.metric("Progression",    round(res["progression_score"], 2))
                    c4.metric("Consistency",    round(res["consistency_score"], 2))

                    score_data_chart = pd.DataFrame({
                        "Score Type": ["Final", "Continuity", "Progression", "Consistency"],
                        "Value": [round(res["final_score"], 2), round(res["continuity_score"], 2),
                                  round(res["progression_score"], 2), round(res["consistency_score"], 2)]
                    })
                    fig = px.bar(score_data_chart, x="Score Type", y="Value", text="Value",
                                 color="Score Type", range_y=[0, 1],
                                 color_discrete_sequence=["#4C8BF5", "#34A853", "#FBBC04", "#EA4335"])
                    fig.update_layout(showlegend=False, height=280, margin=dict(t=20, b=20))
                    fig.update_traces(texttemplate="%{text:.2f}", textposition="outside")
                    st.plotly_chart(fig, use_container_width=True)

                    st.write("🧠 **Interpretation:**", res["interpretation"])
                    st.write("📈 **Career Trajectory:**", res["trajectory"].capitalize())
                    st.write(f"Roles: **{res['total_roles']}** | Unexplained Gaps: **{res['unexplained_gaps_count']}** | Suspicious Overlaps: **{res['suspicious_overlaps_count']}**")

                    # Career Progression table
                    prog = res.get("progression", {})
                    roles = prog.get("roles_analyzed", [])
                    if roles:
                        st.divider()
                        st.subheader("Career Progression")
                        prog_df = pd.DataFrame([{
                            "Title": r["title"], "Organization": r["organization"],
                            "Start": r["start_date"], "Seniority": r["tier_label"], "Tier": r["tier"]
                        } for r in roles])
                        st.dataframe(prog_df, use_container_width=True, hide_index=True)

                    # Gaps
                    gaps = res.get("gaps", [])
                    if gaps:
                        st.divider()
                        st.subheader("Professional Gaps")
                        for g in gaps:
                            icon = "✅" if g["justified"] else "⚠️"
                            st.markdown(f"{icon} **{g['description']}** — *{g['justification']}*")

                    # Overlaps
                    overlaps = res.get("exp_overlaps", [])
                    if overlaps:
                        st.divider()
                        st.subheader("Experience Overlaps")
                        for o in overlaps:
                            icon = "🔴" if o["suspicion"] == "high" else "🟡"
                            st.markdown(f"{icon} **{o['job_a']}** @ {o['org_a']} ↔ **{o['job_b']}** @ {o['org_b']} — {o['note']}")

                    # Missing info + email
                    missing = res.get("missing_info", {})
                    if missing.get("missing_fields"):
                        st.divider()
                        st.subheader("Data Completeness")
                        st.metric("Completeness", round(missing.get("completeness_score", 1.0), 2))
                        st.warning("Missing fields:")
                        for f in missing["missing_fields"]:
                            st.markdown(f"  • {f}")
                        if missing.get("email_draft"):
                            st.subheader("📧 Auto-Generated Follow-Up Email")
                            st.text_area("Email Draft", value=missing["email_draft"], height=300,
                                         label_visibility="collapsed")

            # TAB 9: Conference Analysis
            with tab9:
                st.subheader("🎤 Conference Paper Analysis")
                res = _load_cache(selected_id, "conference_profile")
                if not res:
                    st.info("No conference analysis cached.")
                elif not res.get("has_data"):
                    st.warning(res.get("message", "No conference papers found."))
                else:
                    s = res.get("summary", {})
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Total Papers",    s.get("total_conference_papers", 0))
                    c2.metric("A* Venues",       s.get("a_star_count", 0))
                    c3.metric("First Author",    s.get("first_author_count", 0))
                    c4.metric("Conference Score", round(res.get("conference_score", 0), 2))

                    st.write("🧠 **Overall Interpretation:**", s.get("overall_interpretation", "—"))

                    papers = res.get("papers", [])
                    if papers:
                        # Tier distribution chart
                        tier_counts = {}
                        for p in papers:
                            t = p.get("venue_tier", "unknown")
                            tier_counts[t] = tier_counts.get(t, 0) + 1
                        tier_df = pd.DataFrame({"Tier": list(tier_counts.keys()), "Count": list(tier_counts.values())})
                        fig = px.pie(tier_df, names="Tier", values="Count", title="Conference Tier Distribution",
                                     color_discrete_sequence=px.colors.qualitative.Set2)
                        st.plotly_chart(fig, use_container_width=True)

                        st.divider()
                        st.subheader("Per-Paper Breakdown")
                        for p in papers:
                            tier = p.get("venue_tier", "unknown")
                            icon = "🏆" if tier == "A*" else "🥈" if tier == "A" else "📄"
                            maturity = p.get("venue_maturity")
                            mat_str  = f" (Edition #{maturity})" if maturity else ""
                            indexing = ", ".join(p.get("indexing", [])) or "Unknown"
                            st.markdown(
                                f"{icon} **{p.get('title','—')}**\n\n"
                                f"Venue: *{p.get('venue','—')}*{mat_str} | Year: {p.get('year','—')} | "
                                f"Tier: **{tier}** | Role: {p.get('authorship_role','—').replace('_',' ').title()}\n\n"
                                f"Indexed in: {indexing}\n\n"
                                f"_{p.get('quality_note','')}_"
                            )
                            st.divider()

            # TAB 10: Journal Analysis
            with tab10:
                st.subheader("📰 Journal Paper Analysis")
                res = _load_cache(selected_id, "journal_profile")
                if not res:
                    st.info("No journal analysis cached.")
                elif not res.get("has_data"):
                    st.warning(res.get("message", "No journal papers found."))
                else:
                    s = res.get("summary", {})
                    c1, c2, c3, c4, c5 = st.columns(5)
                    c1.metric("Total Papers",    s.get("total_journal_papers", 0))
                    c2.metric("WoS Indexed",     s.get("wos_count", 0))
                    c3.metric("Scopus Indexed",  s.get("scopus_count", 0))
                    c4.metric("Q1 Papers",       s.get("q1_count", 0))
                    c5.metric("Journal Score",   round(res.get("journal_score", 0), 2))

                    st.write("🧠 **Overall Interpretation:**", s.get("overall_interpretation", "—"))

                    papers = res.get("papers", [])
                    if papers:
                        # Quartile chart
                        q_counts = {}
                        for p in papers:
                            q = p.get("quartile", "unknown")
                            q_counts[q] = q_counts.get(q, 0) + 1
                        q_df = pd.DataFrame({"Quartile": list(q_counts.keys()), "Count": list(q_counts.values())})
                        fig = px.bar(q_df, x="Quartile", y="Count", text="Count",
                                     color="Quartile", title="Quartile Distribution",
                                     color_discrete_sequence=px.colors.qualitative.Bold)
                        fig.update_layout(showlegend=False, height=280)
                        fig.update_traces(textposition="outside")
                        st.plotly_chart(fig, use_container_width=True)

                        st.divider()
                        st.subheader("Per-Paper Breakdown")
                        for p in papers:
                            quartile = p.get("quartile", "unknown")
                            q_color  = {"Q1": "🟢", "Q2": "🟡", "Q3": "🟠", "Q4": "🔴"}.get(quartile, "⚪")
                            wos  = "✅ WoS" if p.get("wos_indexed") else "❌ WoS"
                            scop = "✅ Scopus" if p.get("scopus_indexed") else "❌ Scopus"
                            conf_str = f"Confidence: {p.get('confidence','?')}"
                            st.markdown(
                                f"{q_color} **{p.get('title','—')}**\n\n"
                                f"Journal: *{p.get('venue','—')}* | Year: {p.get('year','—')} | "
                                f"Quartile: **{quartile}** | Publisher: {p.get('publisher','—')}\n\n"
                                f"Indexing: {wos}  {scop} | "
                                f"Role: {p.get('authorship_role','—').replace('_',' ').title()} | {conf_str}\n\n"
                                f"IF: {p.get('impact_factor','—')} | _{p.get('quality_note','')}_"
                            )
                            st.divider()

            # TAB 11: Topic Variability + Co-author Analysis
            with tab11:
                st.subheader("🔬 Research Topics & Co-Author Analysis")
                res = _load_cache(selected_id, "topic_coauthor_profile")
                if not res:
                    st.info("No topic/co-author analysis cached.")
                elif not res.get("has_data"):
                    st.warning(res.get("message", "No publications for analysis."))
                else:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Diversity Score",       round(res.get("diversity_score", 0), 2))
                    c2.metric("Collaboration Score",   round(res.get("collaboration_score", 0), 2))
                    c3.metric("Papers Analyzed",       res.get("total_papers_analyzed", 0))

                    ta = res.get("topic_analysis", {})
                    ca = res.get("coauthor_analysis", {})

                    # Topic section
                    st.divider()
                    st.subheader("Research Themes")
                    st.write(f"**Dominant Topic:** {ta.get('dominant_topic','—')} | "
                             f"**Diversity Label:** {ta.get('diversity_label','—')}")
                    st.write(ta.get("interpretation",""))

                    themes = ta.get("themes", [])
                    if themes:
                        theme_df = pd.DataFrame([{
                            "Theme": t["theme"],
                            "Papers": t["paper_count"],
                            "Share %": round(t["percentage"], 1)
                        } for t in themes])
                        col_t, col_p = st.columns(2)
                        with col_t:
                            st.dataframe(theme_df, use_container_width=True, hide_index=True)
                        with col_p:
                            fig = px.pie(theme_df, names="Theme", values="Papers",
                                         title="Publication Theme Distribution",
                                         color_discrete_sequence=px.colors.qualitative.Pastel)
                            st.plotly_chart(fig, use_container_width=True)

                    # Co-author section
                    st.divider()
                    st.subheader("Co-Author Analysis")
                    cc1, cc2, cc3 = st.columns(3)
                    cc1.metric("Unique Co-Authors",   ca.get("total_unique_coauthors", 0))
                    cc2.metric("Avg Team Size",        ca.get("avg_team_size", 0))
                    cc3.metric("Collab Breadth",       ca.get("collaboration_breadth", "—"))

                    st.write("**Collaboration Style:**", ca.get("collaboration_style", "—"))
                    st.write(ca.get("interpretation", ""))

                    freq = ca.get("most_frequent_local", [])
                    if freq:
                        st.subheader("Recurring Collaborators")
                        freq_df = pd.DataFrame(freq)
                        fig = px.bar(freq_df, x="name", y="paper_count", text="paper_count",
                                     labels={"name": "Co-Author", "paper_count": "Papers Together"},
                                     color_discrete_sequence=["#4C8BF5"])
                        fig.update_layout(height=280, margin=dict(t=20, b=20))
                        fig.update_traces(textposition="outside")
                        st.plotly_chart(fig, use_container_width=True)

            # TAB 12: Supervision / Books / Patents
            with tab12:
                st.subheader("🎓 Supervision, Books & Patents")
                res = _load_cache(selected_id, "supervision_books_patents")
                if not res:
                    st.info("No supervision/books/patents analysis cached.")
                else:
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Supervision Score", round(res.get("supervision_score", 0), 2))
                    c2.metric("Book Score",         round(res.get("book_score", 0), 2))
                    c3.metric("Patent Score",       round(res.get("patent_score", 0), 2))
                    c4.metric("Combined Score",     round(res.get("combined_score", 0), 2))

                    st.write("**Interpretation:**", res.get("interpretation", "—"))

                    # Supervision
                    sup = res.get("supervision", {})
                    st.divider()
                    st.subheader("Student Supervision")
                    sc1, sc2, sc3, sc4 = st.columns(4)
                    sc1.metric("PhD (Main)",   sup.get("phd_main", 0))
                    sc2.metric("MS (Main)",    sup.get("ms_main", 0))
                    sc3.metric("PhD (Co)",     sup.get("phd_co", 0))
                    sc4.metric("MS (Co)",      sup.get("ms_co", 0))
                    if sup.get("source") == "not_found":
                        st.info("Supervision data not found in CV. Candidates may be asked to provide this separately.")

                    # Books
                    books = res.get("books", [])
                    if books:
                        st.divider()
                        st.subheader("Books")
                        st.write(res.get("book_overall_note", ""))
                        for b in books:
                            tier_icon = "🟢" if b.get("publisher_tier") == "Top-tier" else "🟡" if b.get("publisher_tier") == "Mid-tier" else "⚪"
                            st.markdown(
                                f"{tier_icon} **{b.get('title','—')}** — *{b.get('publisher','—')}* "
                                f"({b.get('year','—')}) | Role: {b.get('role','—')} | "
                                f"Publisher Tier: {b.get('publisher_tier','—')}\n\n"
                                f"_{b.get('note','')}_"
                            )

                    # Patents
                    patents = res.get("patents", [])
                    if patents:
                        st.divider()
                        st.subheader("Patents")
                        for pt in patents:
                            st.markdown(f"• **{pt.get('title','—')}** — No. {pt.get('number','—')} ({pt.get('year','—')})")

            # TAB 13: Skill Analysis
            with tab13:
                st.subheader("🛠️ Skill Alignment Analysis")

                # Optional job description input
                with st.expander("📝 Optional: Provide a Job Description for Relevance Analysis"):
                    jd_input = st.text_area(
                        "Paste the target job description here (leave blank to skip)",
                        height=150,
                        key="jd_input"
                    )
                    if st.button("Run Skill Analysis with Job Description"):
                        with st.spinner("Running skill analysis..."):
                            r = analyze_skills(selected_id, job_description=jd_input)
                            store_analysis_cache(selected_id, "skill_profile", r)
                        st.success("Skill analysis updated!")
                        st.rerun()

                res = _load_cache(selected_id, "skill_profile")
                if not res:
                    st.info("No skill analysis cached. Run analysis or re-upload CV.")
                elif not res.get("has_data"):
                    st.warning(res.get("message", "No skills found."))
                else:
                    s = res.get("summary", {})
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Total Skills",            s.get("total_skills", 0))
                    c2.metric("Strongly Evidenced",       s.get("strongly_evidenced_count", 0))
                    c3.metric("Partially Evidenced",      s.get("partially_evidenced_count", 0))
                    c4.metric("Unsupported",              s.get("unsupported_count", 0))
                    st.metric("Skill Credibility Score",  round(res.get("skill_score", 0), 2))

                    st.write("🧠 **Interpretation:**", s.get("overall_interpretation", "—"))

                    # Evidence level donut chart
                    ev_data = {
                        "Strongly Evidenced":  s.get("strongly_evidenced_count", 0),
                        "Partially Evidenced": s.get("partially_evidenced_count", 0),
                        "Weakly Evidenced":    s.get("weakly_evidenced_count", 0),
                        "Unsupported":         s.get("unsupported_count", 0),
                    }
                    ev_df = pd.DataFrame({"Level": list(ev_data.keys()), "Count": list(ev_data.values())})
                    fig = px.pie(ev_df, names="Level", values="Count",
                                 title="Skill Evidence Distribution",
                                 hole=0.4,
                                 color_discrete_map={
                                     "Strongly Evidenced":  "#2ecc71",
                                     "Partially Evidenced": "#f39c12",
                                     "Weakly Evidenced":    "#e67e22",
                                     "Unsupported":         "#e74c3c"
                                 })
                    st.plotly_chart(fig, use_container_width=True)

                    # Per-skill table
                    st.divider()
                    st.subheader("Skill-by-Skill Assessment")
                    assessments = res.get("skill_assessments", [])
                    if assessments:
                        icon_map = {
                            "strongly_evidenced":  "🟢",
                            "partially_evidenced": "🟡",
                            "weakly_evidenced":    "🟠",
                            "unsupported":         "🔴",
                            "unknown":             "⚪"
                        }
                        for a in assessments:
                            ev = a.get("evidence_level", "unknown")
                            icon = icon_map.get(ev, "⚪")
                            src  = ", ".join(a.get("evidence_sources", [])) or "none"
                            rel  = a.get("job_relevance", "not_assessed")
                            st.markdown(
                                f"{icon} **{a['skill']}** — *{ev.replace('_',' ').title()}*\n\n"
                                f"Evidence in: `{src}` | Job Relevance: `{rel}`\n\n"
                                f"_{a.get('evidence_note','')}_"
                            )
                        st.divider()

                    # Candidate Summary (full text)
                    st.subheader("📄 Full Candidate Summary Report")
                    summary_text = generate_candidate_summary(selected_id)
                    st.text_area("Summary", value=summary_text, height=450,
                                 label_visibility="collapsed")
                    st.download_button(
                        "📥 Download Summary",
                        data=summary_text.encode(),
                        file_name=f"talash_summary_candidate_{selected_id}.txt",
                        mime="text/plain"
                    )


# =============================================================================
# PAGE 4: RANKINGS DASHBOARD
# =============================================================================
elif page == "Rankings Dashboard":
    st.title("🏆 Candidate Rankings Dashboard")
    st.info("Candidates are ranked by a weighted score across all analysis modules.")

    ranked = rank_all_candidates()

    if not ranked:
        st.warning("No candidates to rank. Upload CVs first.")
    else:
        # Build display table
        display_rows = []
        for r in ranked:
            sub = r.get("sub_scores", {})
            display_rows.append({
                "Rank":        r["rank"],
                "Name":        r["name"],
                "Score %":     r["total_score_pct"],
                "Suitability": r["suitability"],
                "Education":   sub.get("education", 0),
                "Experience":  sub.get("experience", 0),
                "Journal":     sub.get("journal", 0),
                "Conference":  sub.get("conference", 0),
                "Skills":      sub.get("skills", 0),
                "Email":       r["email"]
            })

        rank_df = pd.DataFrame(display_rows)

        # Color-coded table
        def color_score(val):
            if isinstance(val, float):
                if val >= 0.75: return "background-color: #d5f5e3"
                if val >= 0.55: return "background-color: #fef9e7"
                if val >= 0.35: return "background-color: #fdebd0"
                return "background-color: #fadbd8"
            return ""

        st.dataframe(
            rank_df.style.map(color_score,
                subset=["Education", "Experience", "Journal", "Conference", "Skills"]),
            use_container_width=True,
            hide_index=True
        )

        st.divider()

        # Overall score bar chart
        st.subheader("Overall Score Comparison")
        fig = px.bar(
            rank_df.sort_values("Score %", ascending=True),
            x="Score %", y="Name", orientation="h",
            text="Score %", color="Score %",
            color_continuous_scale=["#e74c3c", "#f39c12", "#2ecc71"],
            range_x=[0, 100]
        )
        fig.update_layout(height=max(300, len(ranked) * 45), margin=dict(t=20, b=20),
                          coloraxis_showscale=False)
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="inside")
        st.plotly_chart(fig, use_container_width=True)

        # Radar / sub-score comparison
        if len(ranked) >= 2:
            st.divider()
            st.subheader("Sub-Score Comparison (Radar View)")
            categories = ["education", "experience", "journal", "conference", "skills"]
            fig_radar = go.Figure()
            for r in ranked[:5]:   # top 5 only to keep chart readable
                sub = r.get("sub_scores", {})
                values = [sub.get(c, 0) for c in categories] + [sub.get(categories[0], 0)]
                fig_radar.add_trace(go.Scatterpolar(
                    r=values,
                    theta=categories + [categories[0]],
                    fill="toself",
                    name=r["name"]
                ))
            fig_radar.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
                showlegend=True,
                height=450
            )
            st.plotly_chart(fig_radar, use_container_width=True)

        # Suitability distribution
        st.divider()
        st.subheader("Suitability Distribution")
        suit_counts = rank_df["Suitability"].value_counts().reset_index()
        suit_counts.columns = ["Suitability", "Count"]
        fig_suit = px.pie(suit_counts, names="Suitability", values="Count",
                          color_discrete_map={
                              "Highly Recommended": "#2ecc71",
                              "Recommended":        "#f1c40f",
                              "Consider":           "#e67e22",
                              "Below Threshold":    "#e74c3c"
                          })
        st.plotly_chart(fig_suit, use_container_width=True)

        # Generate summary for top candidate
        st.divider()
        st.subheader("📄 Top Candidate Summary Report")
        top = ranked[0]
        summary_text = generate_candidate_summary(top["candidate_id"])
        st.text_area("", value=summary_text, height=400, label_visibility="collapsed")
        st.download_button(
            f"📥 Download Top Candidate Summary",
            data=summary_text.encode(),
            file_name=f"talash_top_candidate_{top['name'].replace(' ','_')}.txt",
            mime="text/plain"
        )


# =============================================================================
# PAGE 5: EXPORT DATA
# =============================================================================
elif page == "Export Data":
    st.title("📤 Export Candidate Data")

    candidates = get_all_candidates_summary()
    if not candidates:
        st.warning("No data to export.")
    else:
        df = pd.DataFrame(candidates)

        # Add ranking scores to export
        ranked = rank_all_candidates()
        score_lookup = {r["candidate_id"]: r["total_score_pct"] for r in ranked}
        df["Total Score %"] = df["ID"].map(score_lookup)

        col1, col2 = st.columns(2)
        with col1:
            csv_bytes = df.to_csv(index=False).encode("utf-8")
            st.download_button("Download as CSV", data=csv_bytes,
                               file_name="talash_candidates.csv", mime="text/csv")
        with col2:
            excel_path = "outputs/talash_candidates.xlsx"
            df.to_excel(excel_path, index=False)
            with open(excel_path, "rb") as f:
                st.download_button("Download as Excel", data=f,
                                   file_name="talash_candidates.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        st.divider()
        st.subheader("Data Preview")
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Export all summaries as text
        st.divider()
        st.subheader("Export All Summaries")
        if st.button("Generate All Candidate Summaries"):
            all_summaries = []
            for c in candidates:
                all_summaries.append(generate_candidate_summary(c["ID"]))
                all_summaries.append("\n\n" + "━" * 60 + "\n\n")
            combined = "\n".join(all_summaries)
            st.download_button(
                "📥 Download All Summaries",
                data=combined.encode(),
                file_name="talash_all_summaries.txt",
                mime="text/plain"
            )
