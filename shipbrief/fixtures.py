"""Helpers for saving trimmed fixture feeds (to keep third-party text out of the repo)."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

TEXT_TAGS = {"description", "summary", "content", "encoded"}
MAX_TEXT = 400
MAX_ENTRIES = 20


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def trim_payload(data: bytes, ext: str) -> bytes:
    if ext == ".json":
        doc = json.loads(data)
        keep = ("objectID", "title", "url", "points", "num_comments", "created_at")
        doc = {"hits": [{k: h.get(k) for k in keep} for h in doc.get("hits", [])]}
        return json.dumps(doc, indent=1).encode()
    root = ET.fromstring(data)
    # Cap number of entries
    for parent in root.iter():
        kids = [c for c in list(parent) if _local(c.tag) in ("item", "entry")]
        for c in kids[MAX_ENTRIES:]:
            parent.remove(c)
    for el in root.iter():
        if _local(el.tag) in TEXT_TAGS:
            text = "".join(el.itertext())
            for c in list(el):
                el.remove(c)
            el.text = text[:MAX_TEXT]
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
