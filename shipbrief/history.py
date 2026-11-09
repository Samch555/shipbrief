"""Previously published items, so the daily digest doesn't repeat yesterday's stories."""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

DAY_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")


def recent_item_ids(data_dir: Path, today: date, days: int = 7) -> set[str]:
    """Ids of items published in digests dated strictly before `today` within `days`.

    Re-running on the same day ignores today's own file, so runs are idempotent.
    """
    ids: set[str] = set()
    if not data_dir.exists():
        return ids
    start = today - timedelta(days=days)
    for p in data_dir.iterdir():
        m = DAY_FILE.match(p.name)
        if not m:
            continue
        d = date.fromisoformat(m.group(1))
        if not (start <= d < today):
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for items in (doc.get("sections") or {}).values():
            for it in items:
                if isinstance(it, dict) and "id" in it:
                    ids.add(it["id"])
    return ids
