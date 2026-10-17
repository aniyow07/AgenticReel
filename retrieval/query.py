"""Evidence retrieval and claim support checks on top of the BM25 index."""
from __future__ import annotations

import re

from retrieval.index import ChunkIndex, tokenize
from retrieval.ingestion import Chunk


def build_queries(topic: str, must_include: list[str], questions: list[str]) -> list[str]:
    qs = [topic, *must_include, *questions]
    seen, out = set(), []
    for q in qs:
        q = q.strip()
        if q and q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out


def best_sentence(chunk: Chunk, query: str, max_len: int = 320) -> str:
    """The sentence in the chunk that overlaps the query most; used as the quoted evidence."""
    q = set(tokenize(query))
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", chunk.text) if len(s.strip()) > 20]
    if not sents:
        return chunk.text[:max_len]
    best = max(sents, key=lambda s: (len(q & set(tokenize(s))), -abs(len(s) - 160)))
    return best[:max_len]


def support_score(claim: str, evidence: str) -> float:
    """Share of the claim's content words that appear in the evidence (0..1)."""
    c = set(tokenize(claim))
    if not c:
        return 0.0
    return len(c & set(tokenize(evidence))) / len(c)


def numbers_supported(claim: str, evidence: str) -> bool:
    """Every number in the claim must appear in the evidence; blocks invented statistics."""
    norm = lambda s: s.replace(",", "")  # noqa: E731
    nums = re.findall(r"\d+(?:\.\d+)?", norm(claim))
    ev = norm(evidence)
    return all(re.search(rf"(?<![\d.]){re.escape(n)}(?![\d])", ev) for n in nums)


def verify_claim(index: ChunkIndex, claim: str, threshold: float = 0.6) -> tuple[Chunk | None, str, float]:
    """Find the best evidence for a claim. Returns (chunk, evidence sentence, score)."""
    best = (None, "", 0.0)
    for ch, _ in index.search(claim, k=5, min_score=0.0):
        sent = best_sentence(ch, claim)
        score = max(support_score(claim, sent), support_score(claim, ch.text) * 0.9)
        if not numbers_supported(claim, ch.text):
            score = min(score, threshold - 0.01)
        if score > best[2]:
            best = (ch, sent if support_score(claim, sent) >= 0.3 else ch.text[:320], score)
    return best
