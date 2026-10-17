"""Optional online research adapter (off by default: ONLINE_RESEARCH=true to enable).

Uses the public Wikipedia API (search + plain-text extracts). Every passage keeps
the real article URL; nothing is fabricated if the request fails, the adapter
just returns no documents and the limitation is reported.
"""
from __future__ import annotations

import os

import httpx

from retrieval.ingestion import SourceDoc, read_markdown

API = "https://{lang}.wikipedia.org/w/api.php"
LANG_CODES = {"english": "en", "spanish": "es", "french": "fr", "german": "de", "italian": "it",
              "portuguese": "pt", "hindi": "hi", "dutch": "nl"}


def wikipedia_sources(query: str, language: str = "English", max_pages: int = 2, start_index: int = 1,
                      client: httpx.Client | None = None) -> tuple[list[SourceDoc], list[str]]:
    lang = LANG_CODES.get(language.strip().lower(), "en")
    contact = os.environ.get("AGENTREEL_CONTACT", "").strip()
    if not contact and client is None:
        # Wikimedia's User-Agent policy requires contact details; we do not invent any.
        return [], ["Online research is enabled but AGENTREEL_CONTACT (an email or URL for the Wikimedia "
                    "User-Agent policy) is not set, so it was skipped."]
    ua = f"AgentReel/0.1 (local research tool; contact: {contact}) httpx/{httpx.__version__}"
    http = client or httpx.Client(timeout=20, headers={"User-Agent": ua})
    try:
        r = http.get(API.format(lang=lang), params={"action": "query", "list": "search", "srsearch": query,
                                                    "srlimit": max_pages, "format": "json"})
        r.raise_for_status()
        hits = r.json().get("query", {}).get("search", [])
        docs = []
        for i, h in enumerate(hits, start_index):
            title = h["title"]
            e = http.get(API.format(lang=lang), params={"action": "query", "prop": "extracts", "explaintext": 1,
                                                        "titles": title, "format": "json", "exsectionformat": "wiki"})
            e.raise_for_status()
            pages = e.json().get("query", {}).get("pages", {})
            text = next(iter(pages.values()), {}).get("extract", "")
            if not text.strip():
                continue
            # "== Heading ==" -> markdown headings so sections are kept as metadata
            md = "\n".join(("## " + ln.strip("= ").strip()) if ln.startswith("==") else ln for ln in text.splitlines())
            url = f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}"
            blocks = [b for b in read_markdown(md[:60_000]) if b[0].strip()]
            docs.append(SourceDoc(source_id=f"S{i:03d}", name=url, kind="wikipedia", pages=None, blocks=blocks))
        return docs, []
    except (httpx.HTTPError, ValueError, KeyError) as e:
        return [], [f"Online research failed ({type(e).__name__}); only supplied documents were used."]
