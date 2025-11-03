# AI Job Application Agent – MVP


This MVP takes a job description (paste or URL), pulls the most relevant bullets from your master resume JSON, generates a tailored headline and cover letter in your tone, and exports ATS‑friendly .docx files.

NOTE: This demo version contains a static master resume in data/master_resume.json. Updating this with your own information will provide customized results. A UI for achieving this is forthcoming.

## Quickstart
1) **Clone / copy** this folder.
2) **Create venv** (recommended): `python -m venv .venv && source .venv/bin/activate` (Windows: `.venv\\Scripts\\activate`).
3) **Install deps:** `pip install -r requirements.txt`
4) **Create .env:** copy `.env.example` → `.env`, add your OpenAI key.
5) **Run:** `streamlit run app.py`
6) **Paste a JD** (or URL), preview bullets, click **Generate Package**, then **Download**.


## Notes
- LinkedIn job pages may be blocked; paste the JD text instead when needed.
- Outputs are in `out/` as two .docx files and .txt mirrors.
- Keep your `data/master_resume.json` as the **single source of truth**. Add/edit bullets often, keep them atomic and factual.


## Models
- **Embeddings:** `all-MiniLM-L6-v2` (fast, small) – change in `.env` if desired.
- **Reranker:** `cross-encoder/ms-marco-MiniLM-L-6-v2`.
- **LLM:** `gpt-4o-mini` by default – adjust in `.env`.


## Security/Privacy
- JD text + selected bullets are sent to OpenAI to compose headline and cover letter. The resume bullets are inserted **verbatim** client-side.
- For higher privacy, swap in a local LLM that you host; the interface isolates claims so you can enforce guardrails.