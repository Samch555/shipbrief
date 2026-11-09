"""Prompt-injection hygiene for untrusted fetched text.

All feed content is DATA. These helpers (1) detect instruction-like text so it can be dropped
from summaries, and (2) neutralize markup so data cannot break out of the XML-ish wrapper used
in LLM prompts, and (3) redact secrets from any log line.
"""
from __future__ import annotations

import logging
import os
import re

INJECTION_PATTERNS = re.compile(
    r"(ignore (all |any |the )?(previous|prior|above) (instructions|prompts?)|disregard (the )?(above|previous)"
    r"|system prompt|you are now (chatgpt|claude|an? ai|dan)|act as (an? )?(unfiltered|unrestricted|jailbroken|dan)\b|developer mode|jailbreak"
    r"|<\s*/?\s*(system|instructions?|assistant|user)\s*>|\bBEGIN (SYSTEM|PROMPT)\b|do anything now"
    r"|reveal (your|the) (prompt|instructions)|new instructions\s*:)",
    re.I,
)


def looks_like_injection(text: str) -> bool:
    return bool(INJECTION_PATTERNS.search(text or ""))


def drop_injection_sentences(sentences: list[str]) -> list[str]:
    return [s for s in sentences if not looks_like_injection(s)]


def neutralize(text: str) -> str:
    """Make untrusted text inert inside our prompt wrapper: no angle brackets, no fences."""
    return (text or "").replace("<", "‹").replace(">", "›").replace("```", "'''")


class SecretRedactor(logging.Filter):
    """Logging filter that replaces any configured secret values with ***."""

    ENV_KEYS = ("ANTHROPIC_API_KEY", "GITHUB_TOKEN")

    def __init__(self) -> None:
        super().__init__()
        self.secrets = [v for k in self.ENV_KEYS if (v := os.environ.get(k)) and len(v) >= 8]

    def redact(self, s: str) -> str:
        for sec in self.secrets:
            s = s.replace(sec, "***")
        return re.sub(r"sk-ant-[A-Za-z0-9_\-]{8,}", "sk-ant-***", s)

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self.redact(str(record.msg))
        if record.args:
            record.args = tuple(self.redact(a) if isinstance(a, str) else a for a in record.args)
        return True


def install_log_redaction() -> None:
    f = SecretRedactor()
    root = logging.getLogger()
    root.addFilter(f)
    for h in root.handlers:
        h.addFilter(f)
