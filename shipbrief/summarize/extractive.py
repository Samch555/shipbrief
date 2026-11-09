"""MODE 1 ($0): extractive summaries from the feed's own description, plus deterministic templates.

Rules: at most 2 sentences, at most SUMMARY_MAX_CHARS, boilerplate and instruction-like
sentences removed. When the feed has no usable text, a factual template built only from
fields we fetched (title, version, HN points) is used and marked generatedBy="template".
"""
from __future__ import annotations

import re

from .. import config
from ..models import Item
from ..text import sentences, truncate
from .safety import drop_injection_sentences

BOILERPLATE = re.compile(
    r"(appeared first on|continue reading|read more|click here|subscribe|sign up|newsletter|"
    r"this post|the post .* appeared|full changelog|what's changed|^\W*$|cookie|all rights reserved)",
    re.I,
)
_GH_NOISE = re.compile(r"(@[\w-]+|\(#\d+\)|#\d+|\bby @\S+|https?://\S+|[0-9a-f]{7,40}\b)")


def _clean_sentences(text: str, title: str) -> list[str]:
    out = []
    for s in sentences(text):
        s = s.strip(" -•*")
        if len(s) < 15 or BOILERPLATE.search(s):
            continue
        if s.lower().rstrip(".") == title.lower().rstrip("."):
            continue
        out.append(s)
    return drop_injection_sentences(out)


def _release_summary(it: Item) -> tuple[str, str]:
    project = (it.extra.get("repo") or "").split("/")[-1] or it.source
    version = it.extra.get("version", "")
    notes = _GH_NOISE.sub("", it.raw_summary)
    # Release notes are usually bullet lists; take the first two meaningful lines as highlights.
    bullets = [b.strip(" -*•:") for b in re.split(r"(?:\s[-*•]\s|\n|(?<=[a-z0-9)])\s{2,})", notes)]
    bullets = [b for b in bullets if 12 <= len(b) <= 140 and not BOILERPLATE.search(b)
               and not re.match(r"^((major|minor|patch) changes|features?|bug ?fixes|changes|improvements|fixes|new|added|highlights)\b\W*$", b, re.I)
               and not re.fullmatch(r"[\w.@/=\- ]*\d+\.\d+[\w.]*", b)]
    bullets = drop_injection_sentences(bullets)
    if not version:
        head = f"New {project} release."
    elif re.match(r"^v?\d", version):
        head = f"{project} {version} is out."
    else:  # monorepo package tag such as "@ai-sdk/vue@3.0.326" or "langchain-core==1.7.6"
        head = f"{project} published {version}."
    if bullets:
        hl = "; ".join(truncate(b.rstrip("."), 110) for b in bullets[:2])
        return truncate(f"{head} Highlights: {hl}.", config.SUMMARY_MAX_CHARS), "extractive"
    return head + " See the release notes for details.", "template"


def summarize_item(it: Item) -> tuple[str, str]:
    """Return (summary, generatedBy)."""
    if it.kind == "release":
        return _release_summary(it)
    sents = _clean_sentences(it.raw_summary, it.title)
    if sents:
        text = sents[0]
        if len(sents) > 1 and len(text) + len(sents[1]) < config.SUMMARY_MAX_CHARS:
            text = f"{text} {sents[1]}"
        return truncate(text, config.SUMMARY_MAX_CHARS), "extractive"
    pts = it.extra.get("hnScore")
    if it.source_id == "hn" or pts:
        comments = it.extra.get("comments")
        extra = f" and {comments} comments" if comments else ""
        return (f"Trending on Hacker News with {pts} points{extra}. Open the link for the original source "
                f"and the thread for discussion."), "template"
    return f"New from {it.source}. Open the link to read the original post.", "template"


WHO_BY_TAG = {
    "coding": "Developers who want AI help in their editor or terminal.",
    "agents": "Developers building agents or automating multi-step tasks.",
    "rag": "Teams building search or question-answering over their own documents.",
    "evals": "Teams that need to test prompts and models before shipping.",
    "multimodal": "Designers and builders working with images, audio, or video.",
    "training": "ML engineers fine-tuning or training models.",
    "models": "Anyone running or comparing AI models.",
    "open-source": "Developers who prefer self-hosted, open-source tooling.",
}


def tool_fields(it: Item, summary: str) -> tuple[str, str]:
    """(whatItDoes, whoItsFor) for the Tools section, derived only from fetched text."""
    sents = _clean_sentences(it.raw_summary, it.title)
    if sents:
        what = truncate(sents[0], 280)
    else:
        name = re.sub(r"^(show hn|launch hn)\s*:\s*", "", it.title, flags=re.I)
        what = truncate(name, 280)
    who = next((WHO_BY_TAG[t] for t in it.tags if t in WHO_BY_TAG), "Developers exploring new AI tools.")
    return what, who
