"""AI-relevance scoring, keyword tagging, kind detection, and role inference. Deterministic."""
from __future__ import annotations

import re

from .models import Item

# (pattern, weight). Strong AI terms weigh 1.0, ambiguous ones less.
_AI_TERMS: list[tuple[str, float]] = [
    (r"\bA\.?I\b", 1.0), (r"artificial intelligence", 1.0), (r"\bLLMs?\b", 1.0), (r"language models?", 1.0),
    (r"\bGPT[- ]?\w*", 1.0), (r"\bClaude\b", 1.0), (r"\bGemini\b", 1.0), (r"\bGemma\b", 1.0), (r"\bLlama\b", 1.0),
    (r"\bMistral\b", 1.0), (r"\bDeepSeek\b", 1.0), (r"\bQwen\b", 1.0), (r"\bGrok\b", 0.8), (r"\bPhi-\d", 0.8),
    (r"\bOpenAI\b", 1.0), (r"\bAnthropic\b", 1.0), (r"\bDeepMind\b", 1.0), (r"Hugging ?Face", 1.0),
    (r"machine learning", 1.0), (r"deep learning", 1.0), (r"neural (net|network)", 1.0), (r"\btransformers?\b", 0.6),
    (r"\bagent(s|ic)?\b", 0.7), (r"\bchatbots?\b", 0.9), (r"\bdiffusion\b", 0.6), (r"\bRAG\b", 0.8),
    (r"\bembeddings?\b", 0.7), (r"\binference\b", 0.5), (r"fine[- ]?tun", 0.9), (r"\bprompt(s|ing)?\b", 0.6),
    (r"multimodal", 0.9), (r"reasoning model", 1.0), (r"\bMCP\b", 0.8), (r"model context protocol", 1.0),
    (r"\bCopilot\b", 0.8), (r"\bCursor\b", 0.4), (r"vibe[- ]cod", 0.9), (r"text[- ]to[- ](image|video|speech)", 1.0),
    (r"speech recognition", 0.8), (r"computer vision", 0.8), (r"\bGPUs?\b", 0.3), (r"\bCUDA\b", 0.4),
    (r"\bML\b", 0.7), (r"\bNLP\b", 0.8), (r"open[- ]weights?", 1.0), (r"\bbenchmarks?\b", 0.3),
    (r"\bcodex\b", 0.7), (r"\bollama\b", 1.0), (r"\bvLLM\b", 1.0), (r"\btokens?\b", 0.2), (r"\bRLHF\b", 1.0),
    (r"\bAGI\b", 1.0), (r"\bsuperintelligence\b", 1.0), (r"\bfoundation models?\b", 1.0), (r"\bSora\b", 0.8),
]
_AI_RE = [(re.compile(p, re.I if not p.startswith(r"\bA\.?I") else 0), w) for p, w in _AI_TERMS]

TAG_RULES: dict[str, str] = {
    "models": r"\b(models?|LLMs?|GPT|Claude|Gemini|Gemma|Llama|Mistral|Qwen|DeepSeek|open[- ]weights?|checkpoint)\b",
    "agents": r"\b(agents?|agentic|MCP|tool[- ]use|computer[- ]use|autonomous)\b",
    "coding": r"\b(coding|code|developers?|IDE|copilot|programming|SDK|API)\b",
    "research": r"\b(paper|arxiv|study|researchers?|theorem|dataset)\b",
    "safety": r"\b(safety|alignment|jailbreak|red[- ]team|misuse|security|vulnerab)",
    "multimodal": r"\b(image|video|vision|audio|speech|multimodal|voice)\b",
    "robotics": r"\b(robot|robotics|embodied|humanoid)",
    "policy": r"\b(regulation|policy|law|act|government|copyright|lawsuit|EU)\b",
    "hardware": r"\b(GPU|TPU|chip|accelerator|datacenter|data center|silicon|NVIDIA)\b",
    "evals": r"\b(evals?|evaluation|benchmarks?|leaderboard)\b",
    "open-source": r"\b(open[- ]source|open[- ]weights?|github\.com|apache 2|MIT licen)",
    "rag": r"\b(RAG|retrieval|vector (db|database|store)|embeddings?)\b",
    "training": r"\b(fine[- ]?tun\w*|training|RLHF|RL|post-training|distillation)\b",
    "tools": r"\b(tool|CLI|library|framework|plugin|extension|app)\b",
}
_TAG_RE = {t: re.compile(p, re.I) for t, p in TAG_RULES.items()}

TAG_ROLES = {
    "coding": "developer", "agents": "developer", "open-source": "developer", "tools": "developer",
    "rag": "developer", "training": "researcher", "research": "researcher", "evals": "researcher",
    "policy": "founder", "multimodal": "designer", "models": "everyone", "safety": "everyone",
}

_GH_REPO = re.compile(r"^https?://(www\.)?github\.com/[^/]+/[^/#?]+/?$", re.I)
_LAUNCH = re.compile(r"\b(introduc\w*|launch\w*|announc\w*|releas\w*|now available|unveil\w*|meet|available today|open[- ]sourc\w*)\b", re.I)


def ai_relevance(text: str) -> float:
    return round(sum(w for rx, w in _AI_RE if rx.search(text)), 2)


def infer_tags(item: Item, base: tuple[str, ...] | list[str]) -> list[str]:
    tags = list(dict.fromkeys(base))
    text = item.title + " " + item.raw_summary[:600]
    for t, rx in _TAG_RE.items():
        if t not in tags and rx.search(text):
            tags.append(t)
    return tags[:8]


def infer_kind(item: Item, default: str, source_type: str) -> str:
    title = item.title.strip()
    if source_type == "hn":
        if title.lower().startswith("show hn") or _GH_REPO.match(item.url):
            return "tool"
        if title.lower().startswith(("ask hn", "tell hn")) or "news.ycombinator.com" in item.url:
            return "discussion"
        return "news"
    return default


def is_launch(item: Item) -> bool:
    return bool(_LAUNCH.search(item.title))


def infer_roles(item: Item, base: tuple[str, ...] | list[str]) -> list[str]:
    roles = list(dict.fromkeys(base))
    for t in item.tags:
        r = TAG_ROLES.get(t)
        if r and r not in roles:
            roles.append(r)
    if item.kind in ("release", "tool") and "developer" not in roles:
        roles.append("developer")
    if item.kind == "paper" and "researcher" not in roles:
        roles.append("researcher")
    return roles[:6] or ["everyone"]
