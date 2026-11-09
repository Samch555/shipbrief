import json
from datetime import date, timedelta

from shipbrief import history
from shipbrief.dedupe import dedupe, jaccard
from shipbrief.fetch.runner import fetch_all
from shipbrief.models import Item, item_id
from shipbrief.normalize import filter_relevance, is_stable_release, normalize
from shipbrief.ranking import rank, release_significance, select_diverse
from shipbrief.sources import SourceConfigError, load_sources
from shipbrief.text import title_tokens
from tests.conftest import NOW, UNIT_SOURCES, unit_transport


def _run_core():
    results = fetch_all(list(UNIT_SOURCES.values()), unit_transport, NOW)
    items, nstats = normalize(results, NOW)
    return results, items, nstats


def test_one_failing_source_does_not_break_run():
    def flaky(source, url):
        if source.id == "lab":
            raise TimeoutError("boom")
        return unit_transport(source, url)
    results = fetch_all(list(UNIT_SOURCES.values()), flaky, NOW)
    bad = [r for r in results if not r.ok]
    assert [r.source.id for r in bad] == ["lab"] and "boom" in bad[0].error
    assert sum(len(r.entries) for r in results if r.ok) > 5


def test_normalize_drops_bad_items():
    _, items, stats = _run_core()
    items = filter_relevance(dedupe(items)[0], stats)
    titles = {i.title for i in items}
    assert "Undated post" not in titles and stats.dropped["no-date"] == 1
    assert "Ancient AI post" not in titles and stats.dropped["too-old"] >= 1
    assert "A history of bread baking" not in titles  # HN not-AI filtered
    assert stats.dropped["not-ai"] >= 1
    # releases: rc and nightly dropped, one per repo, most significant wins
    rel = [i for i in items if i.kind == "release"]
    assert [i.extra["version"] for i in rel] == ["v1.5.0"]


def test_html_and_injection_text_is_only_data():
    _, items, _ = _run_core()
    it = next(i for i in items if i.title.startswith("Introducing Example-Model 3"))
    assert "<" not in it.raw_summary and "alert" not in it.raw_summary
    assert it.url.startswith("https://example.com/")


def test_kinds_and_tags():
    _, items, _ = _run_core()
    by_title = {i.title: i for i in items}
    assert by_title["Show HN: A tiny CLI for LLM evals"].kind == "tool"
    assert by_title["Ask HN: How do you test AI agents?"].kind == "discussion"
    paper = next(i for i in items if i.kind == "paper")
    assert "research" in paper.tags and "researcher" in paper.roles


def test_dedupe_merges_hn_onto_official_source():
    _, items, _ = _run_core()
    deduped, stats = dedupe(items)
    assert stats.exact_duplicates == 1
    official = next(i for i in deduped if i.canonical_url == "https://example.com/blog/model-3")
    assert official.source == "Example Lab"
    assert official.extra["hnScore"] == 420
    assert official.extra["discussionUrl"].endswith("id=100")


def _item(title, src="a", weight=1.0, hours_ago=1, kind="news", url=None):
    url = url or f"https://{src}.example/{abs(hash(title))}"
    return Item(id=item_id(url), title=title, url=url, source=src, published_at=NOW - timedelta(hours=hours_ago),
                raw_summary="", tags=[], kind=kind, source_id=src, canonical_url=url, source_weight=weight)


def test_title_clustering():
    a = _item("OpenAI launches GPT-9 with native video reasoning", "openai", 1.8)
    b = _item("OpenAI launches GPT-9 with video reasoning", "hn", 1.0)
    c = _item("Unrelated story about robotics funding", "x", 1.0)
    out, stats = dedupe([b, a, c])
    assert stats.clustered == 1 and len(out) == 2
    primary = next(i for i in out if "GPT-9" in i.title)
    assert primary.source == "openai" and primary.related[0]["source"] == "hn"


def test_releases_never_title_clustered():
    a = _item("langchain 1.2.0", "gh1", kind="release")
    b = _item("langchain 1.2.1", "gh1", kind="release")
    out, _ = dedupe([a, b])
    assert len(out) == 2


def test_jaccard():
    assert jaccard(title_tokens("A B C"), title_tokens("")) == 0.0
    assert jaccard(title_tokens("alpha beta gamma"), title_tokens("alpha beta gamma")) == 1.0


def test_release_significance_and_stability():
    assert release_significance("v2.0.0") == 1.0
    assert release_significance("v2.1.0") == 0.6
    assert release_significance("v2.1.3") == 0.2
    assert release_significance("v2.0.0rc1") == 0.0
    for v in ["b12230", "trunk/abc", "nightly", "v0.24.0-alpha.7", "3.4.0b1", "v0.86.3.dev", "latest", "pr19394-evidence"]:
        assert not is_stable_release(v), v
    for v in ["v1.5.0", "langchain-core==1.7.6", "@ai-sdk/vue@4.0.166", "dotnet-1.28.0", "v2.1.0-vscode"]:
        assert is_stable_release(v), v


def test_ranking_is_transparent_and_deterministic():
    fresh_official = _item("Fresh official", "lab", 1.8, hours_ago=1)
    old_official = _item("Old official", "lab", 1.8, hours_ago=60)
    hn_hot = _item("HN hot", "hn", 1.0, hours_ago=2)
    hn_hot.extra["hnScore"] = 900
    ranked = rank([old_official, hn_hot, fresh_official], NOW)
    assert ranked[0].title == "Fresh official"
    assert ranked[-1].title == "Old official"
    assert set(ranked[0].score_parts) == {"recency", "source", "hn", "release", "coverage", "relevance", "kind"}
    assert abs(sum(ranked[0].score_parts.values()) - ranked[0].score) < 0.01
    assert [i.id for i in rank([hn_hot, fresh_official, old_official], NOW)] == [i.id for i in ranked]


def test_select_diverse_caps_per_source():
    items = [_item(f"lab story {n}", "lab", 1.8, hours_ago=n) for n in range(5)] + [_item("other", "o", 0.5)]
    ranked = rank(items, NOW)
    picked = select_diverse(ranked, 4)
    assert sum(1 for i in picked if i.source_id == "lab") == 2
    assert any(i.source_id == "o" for i in picked)


def test_history_excludes_previous_days_only(tmp_path):
    (tmp_path / "2026-11-08.json").write_text(json.dumps({"sections": {"topStories": [{"id": "a" * 16}]}}))
    (tmp_path / "2026-11-09.json").write_text(json.dumps({"sections": {"topStories": [{"id": "b" * 16}]}}))
    (tmp_path / "2026-10-01.json").write_text(json.dumps({"sections": {"topStories": [{"id": "c" * 16}]}}))
    ids = history.recent_item_ids(tmp_path, date(2026, 11, 9))
    assert ids == {"a" * 16}


def test_sources_yaml_loads_and_validates(tmp_path):
    srcs = load_sources()
    assert len(srcs) >= 40
    assert all(s.url.startswith("https://") for s in srcs)
    gh = [s for s in srcs if s.type == "github_releases"]
    assert 30 <= len(gh) <= 60
    bad = tmp_path / "bad.yaml"
    bad.write_text("sources:\n  - {id: x, name: X, type: ftp, url: 'ftp://x'}\n")
    try:
        load_sources(bad)
        assert False, "should fail"
    except SourceConfigError:
        pass
