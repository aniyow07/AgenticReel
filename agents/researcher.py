"""Agent 2: Researcher / RAG -> facts.json

Evidence comes only from documents and text the user supplied (plus an optional
online adapter, disabled by default). An LLM may *propose* claims from the
retrieved passages, but every claim is re-checked deterministically against the
source text; claims without matching evidence are marked unsupported.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from agents.base import AgentContext, ask_llm
from retrieval.index import ChunkIndex
from retrieval.online import wikipedia_sources
from agents.scriptwriter import clean_topic
from retrieval.ingestion import IngestionError, chunk, load_source, text_source
from retrieval.query import build_queries, support_score, verify_claim
from schemas.artifacts import Fact, Facts, Plan, Source

PROMPT_VERSION = "researcher/v1"

# Sentences about the document itself are not facts about the topic.
META = re.compile(r"\b(this (sample |short )?(document|file|page|note)s?|replace it with|written for testing)\b", re.I)

SYSTEM = """You are the Researcher agent. Using ONLY the numbered source passages provided, write short factual
claims relevant to the video brief. Each claim must be directly supported by one passage; copy numbers exactly.
Do not use outside knowledge, do not invent sources, quotations, URLs or statistics.
Return JSON: {"claims": [{"claim": "...", "passage": <passage number>}]}"""


class ClaimLLM(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)  # LLMs sometimes emit 3 for "3"
    claim: str = Field(min_length=5, max_length=300)
    passage: int


class ClaimsLLM(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)  # LLMs sometimes emit 3 for "3"
    claims: list[ClaimLLM] = Field(default_factory=list, max_length=20)


def ingest(ctx: AgentContext) -> tuple[list, list[Source], list[str]]:
    b = ctx.brief
    docs, problems = [], []
    for i, f in enumerate(b.source_files, 1):
        try:
            docs.append(load_source(f, f"S{i:03d}"))
        except IngestionError as e:
            problems.append(str(e))
    if b.source_text.strip():
        docs.append(text_source(b.source_text, f"S{len(docs) + 1:03d}"))
    if ctx.settings.online_research and ctx.mode != "LOCAL_ONLY" and b.content_type != "fictional_story":
        online, notes = wikipedia_sources(clean_topic(b.topic), b.language, start_index=len(docs) + 1)
        docs.extend(online)
        problems.extend(notes)
        ctx.job.log.log("research", "wikipedia", "ok" if online else "error", pages=[d.name for d in online],
                        error="; ".join(notes) or None)
    # "About this file/document" sections describe the file, not the topic.
    chunks = [c for d in docs for c in chunk(d) if not re.match(r"about this (file|document)", c.heading or "", re.I)]
    sources = [Source(source_id=d.source_id, name=d.name, kind=d.kind, pages=d.pages, chars=d.chars) for d in docs]
    return chunks, sources, problems


USER_PASSAGES = 7  # of the 10 passages shown to the LLM, at most this many from the user's sources when Wikipedia is on


def _tiers(chunks: list, online_ids: set[str]) -> list[ChunkIndex]:
    """One index for the user's own sources, one for online sources; only non-empty ones."""
    own = [c for c in chunks if c.source_id not in online_ids]
    online = [c for c in chunks if c.source_id in online_ids]
    return [ChunkIndex(x) for x in (own, online) if x]


def _verify(tiers: list[ChunkIndex], claim: str) -> tuple:
    """Best evidence for a claim, preferring the user's sources over Wikipedia."""
    best = (None, "", 0.0)
    for tier in tiers:
        found = verify_claim(tier, claim)
        if found[2] > best[2]:
            best = found
        if best[2] >= 0.6:
            break
    return best


def _looks_like_statement(s: str) -> bool:
    return len(s.split()) >= 4


def run(ctx: AgentContext, plan: Plan) -> Facts:
    b = ctx.brief
    chunks, sources, problems = ingest(ctx)
    index = ChunkIndex(chunks)
    if chunks:
        index.save(ctx.job.path("retrieval_index.json"))
    limitations = list(problems)
    facts: list[Fact] = []

    # User-stated points are kept but labelled as user-provided, not independently verified.
    for item in b.must_include:
        if _looks_like_statement(item):
            facts.append(Fact(fact_id=f"F{len(facts) + 1:03d}", claim=item, status="user_provided",
                              evidence="Stated by the user in the brief (not independently verified)."))

    if b.content_type == "fictional_story" and not chunks:
        return Facts(facts=facts, sources=sources, research_performed=False,
                     limitations=limitations + ["Fictional story: no factual research performed."], origin="local")

    if not chunks:
        if plan.research_required:
            limitations.append("No source documents were supplied and online research is disabled, so no factual "
                               "claims could be verified. The script must stay general and avoid specific facts, "
                               "numbers or claims about real organizations.")
        return Facts(facts=facts, sources=sources, research_performed=False, limitations=limitations,
                     origin="local")

    # The user's own sources and Wikipedia are searched separately: in one index the many topic-heavy
    # Wikipedia sections dilute the term weights and push a short PDF below the relevance floor.
    tiers = _tiers(chunks, {s.source_id for s in sources if s.kind == "wikipedia"})
    queries = build_queries(b.topic, b.must_include, plan.research_questions)
    ranked = []
    for tier in tiers:  # user sources first, Wikipedia fills the remaining slots
        hits: dict[str, tuple] = {}
        for q in queries:
            for ch, score in tier.search(q, k=4):
                if ch.chunk_id not in hits or hits[ch.chunk_id][1] < score:
                    hits[ch.chunk_id] = (ch, score, q)
        take = USER_PASSAGES if tier is not tiers[-1] else 10 - len(ranked)
        ranked += sorted(hits.values(), key=lambda x: x[1], reverse=True)[:take]
    if not ranked:
        limitations.append("The supplied sources did not contain passages relevant to the topic.")

    origin = "local"
    proposed: list[str] = []
    if ranked:
        passages = "\n\n".join(f"[{i}] ({c.source}{', p.' + str(c.page) if c.page else ''}) {c.text}"
                               for i, (c, _, _) in enumerate(ranked, 1))
        data = ask_llm(ctx, "research", SYSTEM, f"Brief topic: {b.topic}\nAudience: {b.audience}\n\nPassages:\n"
                       f"{passages}\n\nReturn up to 8 claims.", ClaimsLLM, PROMPT_VERSION, temperature=0.2,
                       max_tokens=1500)
        if data:
            origin = "llm"
            proposed = [c.claim for c in data.claims]
    if not proposed:
        # Local fallback: quote the most relevant sentences of the top passages (no paraphrasing).
        for ch, _, q in ranked[:8]:
            # resumes and slides use bullets instead of full stops: treat bullets as sentence breaks
            text = re.sub(r"\s*[•◦§▪●]\s*", ". ", ch.text)
            sents = [x.strip(" .") + "." for x in re.split(r"(?<=[.!?])\s+", text) if 6 <= len(x.split()) <= 40]
            sents = [x for x in sents if not META.search(x)]
            sents.sort(key=lambda x: -support_score(q, x))
            proposed.extend(sents[:2])
        proposed = proposed[:12]

    seen = set()
    for claim in proposed:
        key = re.sub(r"\W+", " ", claim.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        ch, evidence, score = _verify(tiers, claim)
        fid = f"F{len(facts) + 1:03d}"
        if ch and score >= 0.6:
            facts.append(Fact(fact_id=fid, claim=claim, source_id=ch.source_id, source=ch.source, page=ch.page,
                              heading=ch.heading, evidence=evidence, status="supported"))
        else:
            facts.append(Fact(fact_id=fid, claim=claim, status="unsupported",
                              evidence=evidence if ch else "",
                              source_id=ch.source_id if ch else None, source=ch.source if ch else None))
    unsupported = [f.fact_id for f in facts if f.status == "unsupported"]
    if unsupported:
        limitations.append(f"Claims {unsupported} lacked matching evidence and must not be presented as facts.")
    return Facts(facts=facts, sources=sources, limitations=limitations, research_performed=True, origin=origin)




def ingest_index(ctx: AgentContext) -> None:
    """Rebuild this job's retrieval index (no LLM) when facts were reused from an earlier job."""
    chunks, _, _ = ingest(ctx)
    if chunks:
        ChunkIndex(chunks).save(ctx.job.path("retrieval_index.json"))
