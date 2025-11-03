import re
from typing import List

WHITESPACE_RE = re.compile(r"\s+")

def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\u00A0", " ")
    s = WHITESPACE_RE.sub(" ", s)
    return s.strip()


def extract_keywords(jd_text: str, top_k: int = 64) -> List[str]:
    """Very lightweight keyword extractor: dedup lowercased tokens >2 chars.
    Enough for MVP hybrid retrieval. Swap with spaCy/Rake/KeyBERT later.
    """
    if not jd_text:
        return []
    text = re.sub(r"[^A-Za-z0-9+/#&.,\- ]", " ", jd_text).lower()
    tokens = [t for t in text.split() if len(t) > 2]
    seen = set()
    keywords = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            keywords.append(t)
    return keywords[:top_k]