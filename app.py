# app.py
import os
from pathlib import Path
from dotenv import load_dotenv
import streamlit as st
from collections import defaultdict

from utils.io import read_json, OUT, DATA
from core.jd_parser import fetch_jd_from_url, clean_jd_text
from core.retrieval import HybridRetriever, diversify
from core.reranker import Reranker
from core.llm import compose_package
from core.export_docx import (
    render_resume_docx,
    render_cover_letter_docx,
    write_txt_mirrors,
)

load_dotenv()

st.set_page_config(page_title="AI Job Application Agent", page_icon="🧰", layout="wide")
st.title("AI Job Application Agent – MVP")

# Sidebar: config
st.sidebar.header("Configuration")
openai_model = os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini")
embed_model = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
ce_model = os.getenv("CROSS_ENCODER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

# Load data
master = read_json(DATA / "master_resume.json")
tone = read_json(DATA / "tone_examples.json")

# ------------------------
# Helpers
# ------------------------
def _extract_bullet_ids(llm_out: dict) -> list[str]:
    """Safely pull bullet_ids from llm_out regardless of dict/list shapes."""
    ids: list[str] = []
    resume = llm_out.get("resume", {}) or {}
    sections = resume.get("sections", []) or []
    if isinstance(sections, dict):
        sections = [sections]
    for sec in sections:
        items = (sec or {}).get("items", []) or []
        if isinstance(items, dict):
            items = [items]
        for it in items:
            ids.extend((it or {}).get("bullet_ids", []) or [])
    # unique order-preserving strings
    seen, clean = set(), []
    for i in ids:
        if isinstance(i, str) and i not in seen:
            seen.add(i)
            clean.append(i)
    return clean


@st.cache_resource(show_spinner=False)
def get_retriever():
    r = HybridRetriever(embedding_model=embed_model)
    r.index_from_master(master)
    return r


@st.cache_resource(show_spinner=False)
def get_reranker():
    return Reranker(model_name=ce_model)


retriever = get_retriever()
reranker = get_reranker()

# ------------------------
# 1) Provide Job Description
# ------------------------
st.markdown("### 1) Provide Job Description")
jd_text = st.text_area("Job Description:", height=220)

jd_text = clean_jd_text(jd_text)

if jd_text:
    st.success("JD loaded.")
    with st.expander("Preview JD text"):
        st.write(jd_text)

# ------------------------
# 2) Match & Select Bullets
# ------------------------
st.markdown("### 2) Match & Select Bullets")
chosen = []
if jd_text:
    with st.spinner("Retrieving relevant bullets…"):
        hits = retriever.search(jd_text, top_k=40)
        diversified = diversify(hits, k=24)
        reranked = reranker.rerank(jd_text, diversified, top_k=16)

    st.caption("Top matches (you can uncheck to exclude):")
    for b in reranked:
        checked = st.checkbox(b.text, value=True, key=b.id)
        if checked:
            chosen.append(b)

    st.info(f"Selected {len(chosen)} bullet(s). You can adjust before generating.")

# ------------------------
# 3) Generate Package
# ------------------------
st.markdown("### 3) Generate Package")
company = st.text_input("Company (for filenames)")
role = st.text_input("Role title (for filenames)")

if st.button("Generate Resume + Cover Letter", type="primary", disabled=not (jd_text and chosen)):
    with st.spinner("Composing…"):
        # Include source metadata so the LLM can attribute experiences in the cover letter
        allowed = [
            {
                "id": b.id,
                "text": b.text,
                "meta": {"employer": b.meta.get("employer"), "role": b.meta.get("role")},
            }
            for b in chosen
        ]        # Keep signature compatible with your current core/llm.py
        data = compose_package(jd_text, allowed, tone, model=openai_model)

        # Debug: inspect raw JSON (optional)
        with st.expander("Debug: raw LLM JSON"):
            st.json(data)

        # Preserve model’s bullet order if it provided IDs; otherwise keep UI order
        id2bullet = {b.id: b for b in chosen}
        bullet_ids = _extract_bullet_ids(data)
        if bullet_ids:
            ordered_bullets = [id2bullet[i] for i in bullet_ids if i in id2bullet]
        else:
            ordered_bullets = chosen

        def _dates_to_str(d: dict) -> str:
            if not isinstance(d, dict):
                return ""
            s = d.get("start", ""); e = d.get("end", "")
            return f"{s}–{e}" if (s or e) else ""

        # Group selected bullets by (section_id, item_id)
        groups = defaultdict(list)
        for b in ordered_bullets:
            sec_id = b.meta.get("section_id") or "exp"
            item_id = b.meta.get("item_id") or b.id
            groups[(sec_id, item_id)].append(b)

        # --- Enforce primary bullets + minimum 3 bullets per included item ---
        MIN_BULLETS_PER_ITEM = 3
        sections_map = defaultdict(list)  # title -> list of item dicts

        for (sec_id, item_id), blist in groups.items():
            ref = blist[0]
            title = ref.meta.get("section_title") or "Experience"
            employer_or_name = ref.meta.get("employer") or "Experience"
            role_line = ref.meta.get("role") or ("Project" if title.lower().startswith("project") else "")
            location = ref.meta.get("location") or ""
            dates = _dates_to_str(ref.meta.get("dates", {}))
            if title.lower().startswith("project"):
                # Project name comes from employer_or_name (set to item.name in retrieval)
                project_name_as_title = employer_or_name
                # Aggregate unique skills across bullets for this project
                skill_set = []
                seen = set()
                for b in blist:
                    for s in (b.meta.get("skills") or []):
                        if s and s not in seen:
                            seen.add(s)
                            skill_set.append(s)
                top_skills = skill_set[:3]
                skills_as_employer = " · ".join(top_skills)
                role_line = project_name_as_title
                employer_or_name = skills_as_employer

            # Rank ALL bullets that belong to this item by relevance to JD
            all_ranked = retriever.rank_item_bullets(item_id, jd_text)

            primaries = [b for b in all_ranked if b.meta.get("primary")]
            secondaries = [b for b in all_ranked if not b.meta.get("primary")]

            # Start with ALL primaries (must include, even if user didn’t check them)
            ordered_ids: list[str] = []
            for b in primaries:
                if b.id not in ordered_ids:
                    ordered_ids.append(b.id)

            # Add user-selected non-primary bullets in current (UI/LLM) order
            for b in blist:
                if not b.meta.get("primary") and b.id not in ordered_ids:
                    ordered_ids.append(b.id)

            # Backfill with remaining secondaries by relevance until minimum is met
            for b in secondaries:
                if len(ordered_ids) >= MIN_BULLETS_PER_ITEM:
                    break
                if b.id not in ordered_ids:
                    ordered_ids.append(b.id)

            # Materialize texts in enforced order
            id_to_bullet = {b.id: b for b in (all_ranked + blist)}
            enforced_texts = [id_to_bullet[i].text for i in ordered_ids if i in id_to_bullet]

            sections_map[title].append({
                "employer": employer_or_name,
                "role": role_line,
                "location": location,
                "dates": dates,
                "bullets": enforced_texts,
            })

        # Order sections: Experience first, Projects second, then others
        def _order_key(t: str):
            tl = t.lower()
            if tl == "experience":
                return (0, t)
            if tl.startswith("project"):
                return (1, t)
            return (2, t)

        ordered_titles = sorted(sections_map.keys(), key=_order_key)
        _resume_sections = [{"title": t, "items": sections_map[t]} for t in ordered_titles]

        # --- Always include Education from master JSON ---
        education_items = []
        for section in master.get("sections", []):
            if section.get("id") == "education":
                for edu in section.get("items", []):
                    dates = ""
                    if isinstance(edu.get("dates"), dict):
                        s = edu["dates"].get("start", ""); e = edu["dates"].get("end", "")
                        dates = f"{s}–{e}" if (s or e) else ""
                    education_items.append({
                        "employer": edu.get("institution", "Education"),
                        "role": edu.get("credential", ""),
                        "location": edu.get("location", ""),
                        "dates": dates,
                        "bullets": [],
                    })
                break

        if education_items:
            resume_sections = [{"title": "Education", "items": education_items}] + _resume_sections
            #resume_sections.append({"title": "Education", "items": education_items})
        headline = data.get("resume.headline") or data.get("resume").get("headline")


        resume_struct = {
            "headline": headline,
            "sections": resume_sections,
        }

        cl_struct = data.get(
            "cover_letter",
            {
                "greeting": "Hiring Team",
                "body_paragraphs": ["Thanks for considering my application."],
                "closing": "Sincerely,",
                "signature": master.get("profile", {}).get("full_name", ""),
            },
        )

    # Export files
    slug_company = (company or "Company").replace(" ", "_")
    slug_role = (role or "Role").replace(" ", "_")
    resume_path = OUT / f"Savoy_Nate_Resume_{slug_company}_{slug_role}.docx"
    cl_path = OUT / f"Savoy_Nate_CoverLetter_{slug_company}_{slug_role}.docx"

    render_resume_docx(master.get("profile", {}), resume_struct, resume_path)
    render_cover_letter_docx(master.get("profile", {}), cl_struct, cl_path)

    # Plain-text mirrors for portals
    all_bullets_txt = []
    for sec in resume_struct.get("sections", []):
        for it in sec.get("items", []):
            for bt in it.get("bullets", []):
                all_bullets_txt.append(f"- {bt}")
    resume_txt = (
        f"{master.get('profile', {}).get('full_name','')}\n"
        + (resume_struct.get("headline", ""))
        + ("\n\n" if all_bullets_txt else "")
        + "\n".join(all_bullets_txt)
    )
    cl_txt = "\n\n".join(cl_struct.get("body_paragraphs", []))
#    write_txt_mirrors(resume_txt, cl_txt, resume_path, cl_path)

    st.success("Files generated in ./out. Use the buttons below to download.")
    with open(resume_path, "rb") as f:
        st.download_button("Download Resume (.docx)", f, file_name=resume_path.name)
    with open(cl_path, "rb") as f:
        st.download_button("Download Cover Letter (.docx)", f, file_name=cl_path.name)

    with st.expander("Plain-text mirrors (for paste into portals)"):
        st.code(resume_txt)
        st.code(cl_txt)
