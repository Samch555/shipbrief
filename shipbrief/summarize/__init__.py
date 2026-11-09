"""Summarization layer: chooses MODE 1 or MODE 2 and guarantees every item ends up summarized."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from ..models import Item
from . import extractive, factcheck
from .budget import Budget


def choose_mode() -> str:
    forced = os.environ.get("SHIPBRIEF_MODE", "").strip().lower()
    if forced in ("extractive", "1", "mode1"):
        return "extractive"
    return "llm" if os.environ.get("ANTHROPIC_API_KEY") else "extractive"


@dataclass
class SummaryOutcome:
    mode_requested: str
    mode_used: str                     # extractive | llm | llm-partial
    report: factcheck.FactCheckReport = field(default_factory=factcheck.FactCheckReport)
    budget: Budget | None = None
    llm: Any = None                    # LLMSummarizer when MODE 2
    llm_items: int = 0
    errors: list[str] = field(default_factory=list)


def apply_extractive(it: Item) -> None:
    it.summary, it.generated_by = extractive.summarize_item(it)
    if it.kind == "tool" or it.what_it_does == "":
        what, who = extractive.tool_fields(it, it.summary)
        it.what_it_does = it.what_it_does or what
        it.who_its_for = it.who_its_for or who


def summarize_items(items: list[Item], mode: str, client: Any | None = None,
                    budget: Budget | None = None) -> SummaryOutcome:
    out = SummaryOutcome(mode_requested=mode, mode_used="extractive")
    if mode == "llm":
        from .llm import LLMSummarizer

        out.budget = budget or Budget()
        out.llm = LLMSummarizer(out.budget, client)
        done = out.llm.summarize(items, out.report)
        out.llm_items = len(done)
        out.errors.extend(out.llm.errors)
        if done and len(done) == len(items):
            out.mode_used = "llm"
        elif done:
            out.mode_used = "llm-partial"
    for it in items:
        if not it.summary:
            apply_extractive(it)
        elif not it.what_it_does:
            what, who = extractive.tool_fields(it, it.summary)
            it.what_it_does, it.who_its_for = what, it.who_its_for or who
    return out
