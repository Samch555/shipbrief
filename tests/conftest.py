from datetime import datetime, timezone
from pathlib import Path

import pytest

from shipbrief.sources import Source

UNIT = Path(__file__).parent / "fixtures" / "unit"
NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def now():
    return NOW


def unit_bytes(name: str) -> bytes:
    return (UNIT / name).read_bytes()


def make_source(**kw) -> Source:
    base = dict(id="test", name="Test Source", type="rss", url="https://example.com/feed")
    base.update(kw)
    return Source(**base)


UNIT_SOURCES = {
    "lab": make_source(id="lab", name="Example Lab", url="https://example.com/rss", weight=1.5, tags=("models",)),
    "atom": make_source(id="atom", name="Example Atom", url="https://example.org/atom", weight=1.0),
    "rdf": make_source(id="rdf", name="RDF Feed", url="https://example.net/rdf", weight=0.8),
    "arxiv": make_source(id="arxiv", name="arXiv cs.CL", type="arxiv", kind="paper", url="https://rss.arxiv.org/rss/cs.CL", weight=0.6, tags=("research",), roles=("researcher",)),
    "gh": make_source(id="gh", name="example-agents", type="github_releases", kind="release", repo="example/example-agents", url="https://github.com/example/example-agents/releases.atom", weight=0.9, tags=("agents",)),
    "hn": make_source(id="hn", name="Hacker News", type="hn", kind="discussion", url="https://hn.algolia.com/api/v1/search_by_date", weight=1.0, min_score=80, roles=("developer",)),
}
UNIT_FILES = {"lab": "rss2.xml", "atom": "atom.xml", "rdf": "rdf.xml", "arxiv": "arxiv.xml", "gh": "github.xml", "hn": "hn.json"}


def unit_transport(source, url):
    return unit_bytes(UNIT_FILES[source.id])
