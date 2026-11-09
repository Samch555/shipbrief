"""Per-run LLM budget guard (MODE 2).

Before every call we estimate tokens conservatively (chars / 3 + max_tokens for output) and
refuse the call if it could exceed any remaining limit. After the call the real usage from the
API is recorded. When a call is refused the pipeline falls back to MODE 1 for whatever is left.

Limits come from env vars (set in the workflow) with safe defaults:
  SHIPBRIEF_LLM_MAX_ITEMS          default 40     items sent for per-item summaries
  SHIPBRIEF_LLM_MAX_INPUT_TOKENS   default 80000  per run
  SHIPBRIEF_LLM_MAX_OUTPUT_TOKENS  default 20000  per run
  SHIPBRIEF_LLM_MAX_COST_USD       default 0.10   per run (≈ $3/month at most)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

# USD per million tokens (input, output). Source: Anthropic pricing, checked 2026-11-09.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
}


def _env_num(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = PRICES.get(model, (10.0, 50.0))  # unknown model -> assume expensive
    return input_tokens / 1e6 * pin + output_tokens / 1e6 * pout


def estimate_tokens(text: str) -> int:
    return len(text) // 3 + 50


@dataclass
class Budget:
    max_items: int = field(default_factory=lambda: int(_env_num("SHIPBRIEF_LLM_MAX_ITEMS", 40)))
    max_input_tokens: int = field(default_factory=lambda: int(_env_num("SHIPBRIEF_LLM_MAX_INPUT_TOKENS", 80_000)))
    max_output_tokens: int = field(default_factory=lambda: int(_env_num("SHIPBRIEF_LLM_MAX_OUTPUT_TOKENS", 20_000)))
    max_cost_usd: float = field(default_factory=lambda: _env_num("SHIPBRIEF_LLM_MAX_COST_USD", 0.10))
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    calls: int = 0
    items_sent: int = 0
    exhausted: bool = False
    exhausted_reason: str | None = None
    per_model: dict[str, dict[str, float]] = field(default_factory=dict)

    def allow(self, model: str, prompt_text: str, max_tokens: int, n_items: int = 0) -> bool:
        est_in = estimate_tokens(prompt_text)
        reason = None
        if n_items and self.items_sent + n_items > self.max_items:
            reason = "max-items"
        elif self.input_tokens + est_in > self.max_input_tokens:
            reason = "max-input-tokens"
        elif self.output_tokens + max_tokens > self.max_output_tokens:
            reason = "max-output-tokens"
        elif self.cost + cost_usd(model, est_in, max_tokens) > self.max_cost_usd:
            reason = "max-cost"
        if reason:
            self.exhausted = True
            self.exhausted_reason = self.exhausted_reason or reason
            return False
        return True

    def record(self, model: str, input_tokens: int, output_tokens: int, n_items: int = 0) -> None:
        self.calls += 1
        self.items_sent += n_items
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        c = cost_usd(model, input_tokens, output_tokens)
        self.cost += c
        m = self.per_model.setdefault(model, {"calls": 0, "inputTokens": 0, "outputTokens": 0, "costUsd": 0.0})
        m["calls"] += 1
        m["inputTokens"] += input_tokens
        m["outputTokens"] += output_tokens
        m["costUsd"] = round(m["costUsd"] + c, 6)

    def as_dict(self) -> dict:
        return {
            "calls": self.calls, "itemsSent": self.items_sent,
            "inputTokens": self.input_tokens, "outputTokens": self.output_tokens,
            "estimatedCostUsd": round(self.cost, 6),
            "limits": {"maxItems": self.max_items, "maxInputTokens": self.max_input_tokens,
                       "maxOutputTokens": self.max_output_tokens, "maxCostUsd": self.max_cost_usd},
            "budgetExhausted": self.exhausted, "exhaustedReason": self.exhausted_reason,
            "perModel": self.per_model,
        }
