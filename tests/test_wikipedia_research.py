"""Wikipedia adds to the user's own sources instead of crowding them out (no network: the fetch is stubbed)."""
import json
import random

import pymupdf
import pytest

from agents import planner, researcher
from providers.openrouter import LLMUnavailable
from retrieval.ingestion import SourceDoc, read_markdown

PDF_FACT = "A honey bee colony can hold 60,000 workers in summer."
WIKI_FACT = "Beekeepers in ancient Egypt kept hives in clay pipes."


@pytest.fixture
def bees_pdf(tmp_path):
    pdf = tmp_path / "bees.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((50, 72), "Honey bees make honey by evaporating flower nectar in the hive.\n" + PDF_FACT,
                               fontsize=11)
    doc.save(pdf)
    return pdf


@pytest.fixture
def stub_wikipedia(monkeypatch):
    """A long article where every section mentions bees, like a real Wikipedia page."""
    rnd = random.Random(1)
    words = "wax queen drone pollen flower nectar hive colony forage dance comb larva swarm apiary mite".split()
    sections = [f"## Section {i}\n" + " ".join(f"{'Bees make honey' if i % 4 == 0 else 'Bees use'} and "
                                               f"{' '.join(rnd.sample(words, 6))} here." for _ in range(8))
                for i in range(40)]
    md = "## History\n" + WIKI_FACT + "\n\n" + "\n\n".join(sections)
    calls = []

    def fake(query, language="English", start_index=1, **kw):
        calls.append(query)
        blocks = [b for b in read_markdown(md) if b[0].strip()]
        return [SourceDoc(source_id=f"S{start_index:03d}", name="https://en.wikipedia.org/wiki/Honey_bee",
                          kind="wikipedia", pages=None, blocks=blocks)], []
    monkeypatch.setattr(researcher, "wikipedia_sources", fake)
    return calls


def _ctx(make_ctx, pdf, llm):
    ctx = make_ctx("LOCAL_ONLY", topic="How bees make honey", source_files=[str(pdf)])
    plan = planner.run(ctx)
    ctx.settings.execution_mode, ctx.settings.online_research, ctx.llm = "AI_PREFERRED", True, llm
    return ctx, plan


def test_pdf_passages_come_first_and_both_sources_are_verified(make_ctx, bees_pdf, stub_wikipedia):
    seen = {}

    class FakeLLM:
        def complete_json(self, *, schema, user, **kw):
            seen["prompt"] = user
            return type("C", (), {"data": schema.model_validate({"claims": [
                {"claim": PDF_FACT, "passage": 1}, {"claim": WIKI_FACT, "passage": 2}]})})()
    ctx, plan = _ctx(make_ctx, bees_pdf, FakeLLM())
    facts = researcher.run(ctx, plan)

    assert stub_wikipedia, "Wikipedia was not consulted"
    assert seen["prompt"].split("Passages:\n")[1].startswith("[1] (bees.pdf")
    by_claim = {f.claim: f for f in facts.facts}
    assert by_claim[PDF_FACT].status == "supported" and by_claim[PDF_FACT].source == "bees.pdf"
    assert by_claim[WIKI_FACT].status == "supported" and by_claim[WIKI_FACT].source.startswith("https://en.wikipedia")
    # on-screen grounding reads this index, so it must hold both sources
    indexed = {c["source"] for c in json.loads(ctx.job.path("retrieval_index.json").read_text(encoding="utf-8"))}
    assert indexed == {"bees.pdf", "https://en.wikipedia.org/wiki/Honey_bee"}


def test_local_fallback_still_quotes_the_pdf_when_wikipedia_is_on(make_ctx, bees_pdf, stub_wikipedia):
    class Down:
        def complete_json(self, **kw):
            raise LLMUnavailable("all configured models failed")
    ctx, plan = _ctx(make_ctx, bees_pdf, Down())
    facts = researcher.run(ctx, plan)
    sources = {f.source for f in facts.supported()}
    assert "bees.pdf" in sources and "https://en.wikipedia.org/wiki/Honey_bee" in sources
