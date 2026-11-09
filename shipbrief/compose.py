"""Compose the digest (spec step 7): pick sections, summarize, add prompt + workflow, build JSON.

Each item appears in at most one section. Selection order:
  topStories -> modelsAndAgents -> tools -> openSource -> research
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from . import config
from .models import Item
from .ranking import release_significance, select_diverse
from .summarize import SummaryOutcome, factcheck, summarize_items, templates
from .text import truncate

_MODEL_AGENT_RE = re.compile(r"\b(model|LLM|GPT|Claude|Gemini|Gemma|Llama|Mistral|Qwen|DeepSeek|agent|agentic|"
                             r"reasoning|open[- ]weights?|checkpoint|MCP)\b", re.I)


_LAUNCH_RE = re.compile(r"\b(introduc\w*|launch\w*|releas\w*|now available|available|open[- ]sourc\w*|meet|new|preview|"
                        r"beta|brings|adds|announc\w*|unveil\w*|build with)\b", re.I)


@dataclass
class Sections:
    topStories: list[Item]
    modelsAndAgents: list[Item]
    tools: list[Item]
    openSource: list[Item]
    research: list[Item]

    def all(self) -> list[Item]:
        return self.topStories + self.modelsAndAgents + self.tools + self.openSource + self.research

    def as_dict(self) -> dict[str, list[Item]]:
        return {"topStories": self.topStories, "modelsAndAgents": self.modelsAndAgents, "tools": self.tools,
                "openSource": self.openSource, "research": self.research}


def _top_eligible(it: Item) -> bool:
    if it.kind == "paper":
        return False
    if it.kind == "release":
        return release_significance(it.extra.get("version", "")) >= 1.0  # only major releases make top stories
    return True


def select_sections(ranked: list[Item]) -> Sections:
    used: set[str] = set()

    def take(pool: list[Item], n: int, max_per_source: int = 2) -> list[Item]:
        picked = select_diverse(pool, n, exclude=used, max_per_source=max_per_source)
        used.update(i.id for i in picked)
        return picked

    top = take([i for i in ranked if _top_eligible(i)], config.TOP_STORIES_MAX)
    models = take([i for i in ranked if i.kind in ("news", "discussion")
                   and ("models" in i.tags or "agents" in i.tags) and _MODEL_AGENT_RE.search(i.title)],
                  config.MODELS_AGENTS_MAX)
    tools = take([i for i in ranked if i.kind == "tool"
                  or (i.kind in ("news", "discussion") and ({"tools", "coding"} & set(i.tags)) and _LAUNCH_RE.search(i.title))],
                 config.TOOLS_MAX)
    if len(tools) < 2:
        # Quiet day: promote notable (minor/major) releases of developer tools into "Tools worth trying".
        extra = [i for i in ranked if i.kind == "release" and release_significance(i.extra.get("version", "")) >= 0.6]
        tools += take(extra, 2 - len(tools), max_per_source=1)
    oss = take([i for i in ranked if i.kind == "release"], config.OPEN_SOURCE_MAX, max_per_source=1)
    research = take([i for i in ranked if i.kind == "paper"], config.RESEARCH_MAX, max_per_source=2)
    return Sections(top, models, tools, oss, research)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def item_json(it: Item, tool: bool = False) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": it.id,
        "title": truncate(it.title, 300),
        "url": it.url,
        "source": it.source[:120],
        "sourceId": it.source_id,
        "publishedAt": _iso(it.published_at),
        "kind": it.kind,
        "tags": [t for t in it.tags if re.fullmatch(r"[a-z0-9-]{1,32}", t)][:8],
        "roles": (it.roles or ["everyone"])[:6],
        "summary": truncate(it.summary, 400),
        "generatedBy": it.generated_by or "extractive",
        "score": it.score,
    }
    if it.extra.get("version"):
        d["version"] = str(it.extra["version"])[:80]
    if it.extra.get("hnScore"):
        d["hnScore"] = int(it.extra["hnScore"])
    if it.extra.get("discussionUrl") and it.extra["discussionUrl"] != it.url:
        d["discussionUrl"] = it.extra["discussionUrl"]
    if it.related:
        d["related"] = [{"source": r["source"][:120], "url": r["url"], "title": truncate(r.get("title", ""), 300)}
                        for r in it.related[:6]]
    if tool or it.kind == "tool":
        d["whatItDoes"] = truncate(it.what_it_does or it.summary or it.title, 300)
        d["whoItsFor"] = truncate(it.who_its_for or "Developers exploring new AI tools.", 200)
    return d


def _based_on(it: Item) -> dict[str, str]:
    return {"itemId": it.id, "title": truncate(it.title, 300), "url": it.url}


def _anchor_item(items: list[Item], prefer_tags: list[str]) -> Item:
    for t in prefer_tags:
        for it in items:
            if t in it.tags:
                return it
    return items[0]


def _template_extras(sections: Sections, day: date) -> tuple[dict, dict]:
    candidates = sections.topStories + sections.modelsAndAgents + sections.tools
    p_item = _anchor_item(candidates or sections.all(), templates.TAG_PRIORITY)
    prompt = templates.prompt_for(p_item.title, p_item.tags, day)
    prompt.update(basedOn=_based_on(p_item), generatedBy="template")
    w_pool = sections.tools + sections.openSource + sections.modelsAndAgents + sections.topStories
    w_item = _anchor_item(w_pool or sections.all(), ["coding", "agents", "open-source", "models", "research"])
    wf = templates.workflow_for(w_item.tags, day)
    wf.update(basedOn=_based_on(w_item), generatedBy="template")
    return prompt, wf


def _llm_extras(outcome: SummaryOutcome, sections: Sections) -> tuple[str | None, dict | None, dict | None]:
    """Ask Sonnet for headline/prompt/workflow; validate each piece; return None for rejected parts."""
    items = sections.all()
    data = outcome.llm.compose(items)
    if not data:
        return None, None, None
    by_id = {i.id: i for i in items}
    model = "claude-sonnet-5-5"
    headline = " ".join(str(data.get("headline", "")).split())[:200] or None
    if headline and (factcheck.check_summary(headline, "\n".join(i.source_text for i in items)) or len(headline) > 160):
        outcome.report.summaries_rejected.append({"id": "headline", "reason": "headline-check"})
        headline = None

    prompt = None
    p = data.get("promptOfTheDay") or {}
    p_item = by_id.get(str(p.get("basedOnId")))
    p_text = str(p.get("prompt", "")).strip()
    reason = factcheck.check_generated_text(p_text, config.PROMPT_MAX_WORDS) if p_text else "empty"
    if p_item and not reason and len(p_text) >= 20 and p.get("roles"):
        prompt = {"title": str(p.get("title", "Prompt of the day"))[:120] or "Prompt of the day",
                  "prompt": p_text[:1200], "useCase": str(p.get("useCase", ""))[:300] or f"Inspired by: {p_item.title}"[:300],
                  "roles": [r for r in p["roles"] if r in config.ROLES] or ["everyone"],
                  "basedOn": _based_on(p_item), "generatedBy": model}
    else:
        outcome.report.summaries_rejected.append({"id": "promptOfTheDay", "reason": reason or "bad-basedOn"})

    wf = None
    w = data.get("tryThisToday") or {}
    w_item = by_id.get(str(w.get("basedOnId")))
    steps = [" ".join(str(s).split())[:300] for s in (w.get("steps") or []) if str(s).strip()]
    w_reason = next((r for r in (factcheck.check_generated_text(s) for s in steps) if r), None)
    if w_item and 2 <= len(steps) <= 6 and not w_reason and w.get("roles"):
        wf = {"title": str(w.get("title", "Try this today"))[:120] or "Try this today", "steps": steps,
              "roles": [r for r in w["roles"] if r in config.ROLES] or ["everyone"],
              "basedOn": _based_on(w_item), "generatedBy": model}
    else:
        outcome.report.summaries_rejected.append({"id": "tryThisToday", "reason": w_reason or "bad-shape"})
    return headline, prompt, wf


@dataclass
class ComposeResult:
    digest: dict[str, Any]
    sections: Sections
    outcome: SummaryOutcome


def compose(ranked: list[Item], *, day: date, now: datetime, mode: str, records: set[tuple[str, str]],
            stats: dict[str, int], client: Any = None, budget: Any = None) -> ComposeResult:
    sections = select_sections(ranked)

    # Provenance guard BEFORE spending anything on summaries.
    report = factcheck.FactCheckReport()
    for name, items in sections.as_dict().items():
        kept = []
        for it in items:
            if factcheck.check_provenance(it.url, it.published_at.isoformat(), records):
                kept.append(it)
            else:
                report.provenance_rejected.append(it.id)
        setattr(sections, name, kept)

    outcome = summarize_items(sections.all(), mode, client=client, budget=budget)
    outcome.report.provenance_rejected.extend(report.provenance_rejected)

    prompt, wf = _template_extras(sections, day)
    headline = sections.topStories[0].title if sections.topStories else ""
    if outcome.llm is not None and not outcome.budget.exhausted:
        h, p, w = _llm_extras(outcome, sections)
        headline = h or headline
        prompt = p or prompt
        wf = w or wf

    published = len({i.id for i in sections.all()})
    digest = {
        "schemaVersion": config.SCHEMA_VERSION,
        "date": day.isoformat(),
        "generatedAt": _iso(now),
        "product": {"name": config.PRODUCT_NAME, "siteUrl": config.SITE_URL,
                    "feedUrl": config.SITE_URL.rstrip("/") + "/feed.xml"},
        "summaryMode": outcome.mode_used,
        "headline": truncate(headline, 200),
        "stats": {
            "itemsFetched": stats.get("itemsFetched", 0),
            "itemsAfterDedupe": stats.get("itemsAfterDedupe", 0),
            "itemsPublished": published,
            "sourcesOk": stats.get("sourcesOk", 0),
            "sourcesFailed": stats.get("sourcesFailed", 0),
        },
        "sections": {
            "topStories": [item_json(i) for i in sections.topStories],
            "modelsAndAgents": [item_json(i) for i in sections.modelsAndAgents],
            "tools": [item_json(i, tool=True) for i in sections.tools],
            "openSource": [item_json(i) for i in sections.openSource],
            "research": [item_json(i) for i in sections.research],
        },
        "promptOfTheDay": prompt,
        "tryThisToday": wf,
    }
    return ComposeResult(digest=digest, sections=sections, outcome=outcome)
