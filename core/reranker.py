from __future__ import annotations
from typing import List, Tuple
from sentence_transformers import CrossEncoder
from .retrieval import Bullet

class Reranker:
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, candidates: List[Bullet], top_k: int = 12) -> List[Bullet]:
        pairs = [(query, c.text) for c in candidates]
        scores = self.model.predict(pairs)
        ranked = sorted(zip(candidates, scores), key=lambda x: -x[1])
        return [c for c, _ in ranked[:top_k]]
