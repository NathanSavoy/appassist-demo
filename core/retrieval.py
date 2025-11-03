# core/retrieval.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any

import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from utils.text import extract_keywords, normalize_text

@dataclass
class Bullet:
    id: str
    text: str
    meta: Dict[str, Any]


class HybridRetriever:
    def __init__(self, embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.embed = SentenceTransformer(embedding_model)
        self._bm25 = None
        self._corpus_tokens = None
        self._embeddings = None
        self._bullets: List[Bullet] = []
        self._item_to_idx: Dict[str, List[int]] = {}

    def index_from_master(self, master: Dict[str, Any]):
        bullets: List[Bullet] = []
        self._item_to_idx = {}
        for section in master.get("sections", []):
            for item in section.get("items", []):
                for b in item.get("bullets", []):
                    txt = normalize_text(b.get("text", ""))
                    if not txt:
                        continue
                    meta = {
                        "section_id": section.get("id"),
                        "section_title": section.get("title"),
                        "item_id": item.get("id"),
                        "employer": item.get("employer") or item.get("name"),
                        "role": item.get("role"),
                        "location": item.get("location"),
                        "dates": item.get("dates", {}),
                        "skills": b.get("skills", []),
                        "domains": b.get("domains", []),
                        "primary": bool(b.get("primary", False)),
                    }
                    bullets.append(Bullet(id=b.get("id"), text=txt, meta=meta))
                    idx = len(bullets) - 1
                    self._item_to_idx.setdefault(item.get("id") or "", []).append(idx)

        self._bullets = bullets
        # BM25
        tokenized_corpus = [normalize_text(b.text).lower().split() for b in bullets]
        self._bm25 = BM25Okapi(tokenized_corpus)
        self._corpus_tokens = tokenized_corpus
        # Embeddings
        self._embeddings = self.embed.encode([b.text for b in bullets], normalize_embeddings=True)

    def search(self, jd_text: str, top_k: int = 30) -> List[Tuple[Bullet, float]]:
        assert self._bm25 is not None and self._embeddings is not None
        # Query tokens for BM25
        keywords = extract_keywords(jd_text, top_k=128)
        bm25_scores = self._bm25.get_scores(keywords)
        # Embedding query
        q_emb = self.embed.encode([jd_text], normalize_embeddings=True)[0]
        cos = (self._embeddings @ q_emb)
        # Hybrid score (weighted sum)
        bm25_norm = (bm25_scores - bm25_scores.min()) / (bm25_scores.ptp() + 1e-6)
        cos_norm = (cos - cos.min()) / (cos.ptp() + 1e-6)
        hybrid = 0.6 * cos_norm + 0.4 * bm25_norm
        idx = np.argsort(-hybrid)[:top_k]
        results = [(self._bullets[i], float(hybrid[i])) for i in idx]
        return results

    def rank_item_bullets(self, item_id: str, query_text: str) -> List[Bullet]:
        """Return all bullets for a given item_id, ranked by semantic similarity to the JD."""
        idxs = self._item_to_idx.get(item_id or "", []) or []
        if not idxs:
            return []
        q_emb = self.embed.encode([query_text], normalize_embeddings=True)[0]
        subset = [(i, float(self._embeddings[i] @ q_emb)) for i in idxs]
        subset.sort(key=lambda t: -t[1])
        return [self._bullets[i] for i, _ in subset]


def diversify(bullets: List[Tuple[Bullet, float]], k: int = 12) -> List[Bullet]:
    # Simple diversity by limiting near-duplicate starts and employer repetition
    selected: List[Bullet] = []
    seen_starts = set()
    seen_emp: Dict[str, int] = {}
    for b, _ in bullets:
        start = b.text[:40].lower()
        emp = b.meta.get("employer")
        if start in seen_starts:
            continue
        if emp:
            c = seen_emp.get(emp, 0)
            if c >= 6:
                continue
            seen_emp[emp] = c + 1
        seen_starts.add(start)
        selected.append(b)
        if len(selected) >= k:
            break
    return selected
