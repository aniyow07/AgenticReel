"""Small local BM25 index over source chunks (no vector database, no hosted embeddings)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from rank_bm25 import BM25Plus

from retrieval.ingestion import Chunk

STOP = set("""a an the and or but if then of to in on for with by from at as is are was were be been being this that
these those it its into about over under than so such can could should would will may might do does did not no
yes you your we our they their he she his her them i me my what which who whom how why when where""".split())


_SUFFIXES = ("ations", "ation", "ingly", "ing", "edly", "ies", "ied", "ers", "ed", "es", "er", "ly", "s")


def stem(t: str) -> str:
    """Very light suffix stripping so "procrastinating" matches "procrastinate"."""
    for suf in _SUFFIXES:
        if len(t) > len(suf) + 3 and t.endswith(suf):
            t = t[: -len(suf)]
            break
    return t.rstrip("e") if len(t) > 4 else t


def tokenize(text: str) -> list[str]:
    toks = re.findall(r"[\w']+", text.lower())
    return [stem(t) for t in toks if t not in STOP and len(t) > 1]


class ChunkIndex:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        # BM25+ keeps IDF positive, so a single uploaded document (one or few chunks) still ranks sensibly.
        self._tokens = [tokenize(c.text + " " + (c.heading or "")) for c in chunks]
        self._bm25 = BM25Plus(self._tokens) if chunks else None

    def search(self, query: str, k: int = 5, min_score: float = 0.5) -> list[tuple[Chunk, float]]:
        """Top-k chunks sharing at least one content word with the query (min_score is a BM25+ floor)."""
        if not self._bm25:
            return []
        q = tokenize(query)
        if not q:
            return []
        qs = set(q)
        scores = self._bm25.get_scores(q)
        ranked = sorted((x for x in zip(self.chunks, scores, self._tokens) if qs & set(x[2])),
                        key=lambda x: x[1], reverse=True)
        return [(c, float(s)) for c, s, _ in ranked[:k] if s >= min_score]

    def save(self, path: Path) -> None:
        path.write_text(json.dumps([c.to_dict() for c in self.chunks], ensure_ascii=False, indent=1),
                        encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "ChunkIndex":
        return cls([Chunk(**d) for d in json.loads(path.read_text(encoding="utf-8"))])


