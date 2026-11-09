from datetime import datetime, timezone

import pytest

from shipbrief.fetch import parsers
from shipbrief.text import canonical_url, clean_text, sentences, strip_html, truncate
from tests.conftest import unit_bytes


def test_rss2_basic():
    entries = parsers.parse_feed(unit_bytes("rss2.xml"))
    assert len(entries) == 5
    first = entries[0]
    assert first["title"] == "Introducing Example-Model 3 & new API"
    assert first["url"].startswith("https://example.com/blog/model-3")
    assert first["publishedAt"] == datetime(2026, 11, 9, 8, 0, tzinfo=timezone.utc)
    assert entries[1]["publishedAt"] == datetime(2026, 11, 9, 6, 0, tzinfo=timezone.utc)  # dc:date
    assert entries[2]["publishedAt"] is None
    assert entries[4]["url"] == "https://example.com/blog/guid-only"  # guid fallback


def test_atom_prefers_alternate_link_and_published():
    entries = parsers.parse_feed(unit_bytes("atom.xml"))
    assert entries[0]["url"] == "https://example.org/posts/finetune"
    assert entries[0]["publishedAt"].hour == 7
    # updated-only entry, with timezone conversion to UTC
    assert entries[1]["publishedAt"] == datetime(2026, 11, 8, 10, 0, tzinfo=timezone.utc)
    assert "LLM" in entries[1]["summaryHtml"]  # xhtml content


def test_rdf():
    entries = parsers.parse_feed(unit_bytes("rdf.xml"))
    assert len(entries) == 1 and entries[0]["url"] == "https://example.net/a"


def test_arxiv_keeps_only_new_and_strips_preamble():
    entries = parsers.parse_arxiv(unit_bytes("arxiv.xml"))
    assert [e["url"] for e in entries] == ["https://arxiv.org/abs/2611.00001"]
    assert entries[0]["summaryHtml"].startswith("We propose")
    assert entries[0]["publishedAt"] == datetime(2026, 11, 9, 5, 0, tzinfo=timezone.utc)


def test_github_releases_version_and_title():
    entries = parsers.parse_github_releases(unit_bytes("github.xml"), "example/example-agents")
    versions = [e["extra"]["version"] for e in entries]
    assert versions == ["v2.0.0rc1", "v1.5.0", "v1.4.3", "nightly"]
    assert entries[1]["title"] == "example-agents v1.5.0"
    assert entries[2]["title"] == "example-agents: Bugfix release"


def test_hn_algolia_filters_score_and_bad_ids():
    entries = parsers.parse_hn_algolia(unit_bytes("hn.json"), min_score=80)
    titles = [e["title"] for e in entries]
    assert "Low score AI thing" not in titles
    assert "Bad id" not in titles
    ask = next(e for e in entries if e["title"].startswith("Ask HN"))
    assert ask["url"] == "https://news.ycombinator.com/item?id=102"
    assert entries[0]["extra"]["hnScore"] == 420


def test_invalid_xml_raises():
    with pytest.raises(parsers.ParseError):
        parsers.parse_feed(b"<html><body>not a feed")
    with pytest.raises(parsers.ParseError):
        parsers.parse_feed(b"<!DOCTYPE html><html")


def test_strip_html_removes_scripts_and_controls():
    out = clean_text("<p>Hello <b>world</b></p><script>evil()</script>‮​ok &amp; done")
    assert out == "Hello world ok & done"
    assert "evil" not in strip_html("<style>x{}</style><script>evil()</script>")


def test_sentences_and_truncate():
    s = sentences("It works, e.g. on Macs. Second one! Third?")
    assert s == ["It works, e.g. on Macs.", "Second one!", "Third?"]
    assert truncate("a" * 10 + " bbbbbb", 12).endswith("…")


@pytest.mark.parametrize("a,b", [
    ("http://www.Example.com/post/?utm_source=x&b=2&a=1#frag", "https://example.com/post?a=1&b=2"),
    ("https://arxiv.org/pdf/2611.00001v2", "https://arxiv.org/abs/2611.00001"),
    ("https://arxiv.org/abs/2611.00001v1", "https://arxiv.org/abs/2611.00001"),
    ("https://news.ycombinator.com/item?id=5&foo=bar", "https://news.ycombinator.com/item?id=5"),
])
def test_canonical_url(a, b):
    assert canonical_url(a) == b
