from __future__ import annotations
import re
from typing import Optional
import requests
from bs4 import BeautifulSoup
from utils.text import normalize_text

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0 Safari/537.36"
    )
}

SITE_PATTERNS = {
    "indeed": re.compile(r"indeed\\.com/jobs?/view/|indeed\\.com/q-", re.I),
    "linkedin": re.compile(r"linkedin\\.com/jobs", re.I),
}


def fetch_jd_from_url(url: str, timeout: int = 10) -> Optional[str]:
    """Best-effort JD fetcher. LinkedIn may require auth; returns None on failure."""
    try:
        resp = requests.get(url, headers=UA, timeout=timeout)
        if resp.status_code != 200:
            return None
        html = resp.text
        # Heuristics for Indeed / generic pages
        soup = BeautifulSoup(html, "html.parser")
        # Try common containers
        candidates = [
            {"name": "Indeed", "nodes": soup.select('[id*="jobDescriptionText"], .jobsearch-JobComponent-description')},
            {"name": "GenericMain", "nodes": soup.select("main, article")},
            {"name": "Fallback", "nodes": [soup.body] if soup.body else []},
        ]
        for group in candidates:
            for node in group["nodes"]:
                text = node.get_text(" ") if node else ""
                text = normalize_text(text)
                # crude sanity check: at least 300 chars and includes keywords
                if len(text) > 300 and any(k in text.lower() for k in ["responsibilities", "requirements", "qualifications", "role"]):
                    return text
        # Fallback to whole page text
        text = normalize_text(soup.get_text(" "))
        return text if len(text) > 300 else None
    except Exception:
        return None


def clean_jd_text(raw: str) -> str:
    if not raw:
        return ""
    raw = normalize_text(raw)
    # Light section markers for readability
    raw = re.sub(r"(Responsibilities|Requirements|Qualifications)", r"\n\n**\\1**\n", raw, flags=re.I)
    return raw.strip()