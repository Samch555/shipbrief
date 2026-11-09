"""Central constants. Anything tunable lives here (ranking weights live in ranking.py)."""
from __future__ import annotations

import os
from pathlib import Path

PRODUCT_NAME = "ShipBrief"
SCHEMA_VERSION = "1.0.0"
INDEX_SCHEMA_VERSION = "1.0.0"
HEALTH_SCHEMA_VERSION = "1.0.0"

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "schema"
DEFAULT_SOURCES = ROOT / "sources.yaml"
DEFAULT_DATA_DIR = ROOT / "data"
FIXTURES_DIR = ROOT / "tests" / "fixtures"

# Public URLs (set by the workflow; harmless defaults for local runs).
SITE_URL = os.environ.get("SHIPBRIEF_SITE_URL", "https://example.github.io/shipbrief/")
USER_AGENT = (
    "ShipBriefBot/1.0 (+https://github.com/; daily AI digest; respects robots.txt)"
)

# Fetching
HTTP_TIMEOUT_SECONDS = 15
HTTP_RETRIES = 2              # retries after the first attempt
HTTP_BACKOFF_SECONDS = 1.5
MAX_RESPONSE_BYTES = 5_000_000
MAX_ITEMS_PER_SOURCE = 30
MAX_ITEM_AGE_HOURS = 96       # ignore anything older (covers weekends; repeats are removed via history)
FUTURE_SKEW_HOURS = 12        # tolerate small clock skew in feeds

# Publishing gates
MIN_ITEMS_TO_PUBLISH = 8      # fewer ranked items than this -> do not publish
MIN_TOP_STORIES = 3
ARCHIVE_DAYS = 90

# Section sizes
TOP_STORIES_MAX = 8
TOP_STORIES_MIN = 5
MODELS_AGENTS_MAX = 6
TOOLS_MAX = 5
OPEN_SOURCE_MAX = 10
RESEARCH_MAX = 3

# Text limits
SUMMARY_MAX_CHARS = 320
PROMPT_MAX_WORDS = 150

ROLES = ("developer", "researcher", "product", "founder", "designer", "everyone")
