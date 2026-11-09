import json
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

import pytest

from shipbrief import config, publish
from shipbrief.__main__ import _fixture_now
from shipbrief.fetch.runner import FixtureTransport
from shipbrief.pipeline import EXIT_INVALID, EXIT_OK, EXIT_TOO_FEW, run
from shipbrief.validate import validate_digest, validate_index
from tests.conftest import NOW, UNIT_SOURCES, unit_transport

LIVE = config.FIXTURES_DIR / "live"


def _live_run(tmp_path, **kw):
    return run(transport=FixtureTransport(LIVE), now=_fixture_now(LIVE), data_dir=tmp_path / "data",
               feed_path=tmp_path / "feed.xml", mode="extractive", **kw)


def test_offline_end_to_end_publishes_valid_digest(tmp_path):
    res = _live_run(tmp_path)
    assert res.exit_code == EXIT_OK, res.health["failureReason"]
    d = json.loads((tmp_path / "data" / "latest.json").read_text())
    assert validate_digest(d, now=_fixture_now(LIVE)) == []
    assert 5 <= len(d["sections"]["topStories"]) <= 8
    assert d["sections"]["research"] and d["sections"]["openSource"]
    # every item links to a source and appears once
    ids = [i["id"] for s in d["sections"].values() for i in s]
    assert len(ids) == len(set(ids))
    assert all(i["url"].startswith("http") for s in d["sections"].values() for i in s)
    assert (tmp_path / "data" / f"{d['date']}.json").exists()
    assert validate_index(json.loads((tmp_path / "data" / "index.json").read_text())) == []
    health = json.loads((tmp_path / "data" / "health.json").read_text())
    assert health["status"] == "published" and len(health["sources"]) >= 70


def test_feed_is_valid_atom_and_links_sources(tmp_path):
    _live_run(tmp_path)
    root = ET.parse(tmp_path / "feed.xml").getroot()
    ns = {"a": "http://www.w3.org/2005/Atom"}
    entries = root.findall("a:entry", ns)
    assert len(entries) == 1
    content = entries[0].find("a:content", ns).text
    assert "href=" in content and "<script" not in content


def test_idempotent_rerun_same_day(tmp_path):
    first = _live_run(tmp_path).digest
    second = _live_run(tmp_path).digest
    strip = lambda d: {k: v for k, v in d.items() if k != "generatedAt"}
    assert strip(first) == strip(second)


def test_next_day_does_not_repeat_items(tmp_path):
    first = _live_run(tmp_path).digest
    res = run(transport=FixtureTransport(LIVE), now=_fixture_now(LIVE) + timedelta(hours=6, days=0),
              data_dir=tmp_path / "data", feed_path=tmp_path / "feed.xml", mode="extractive")
    # same day -> same digest (history ignores today); simulate tomorrow:
    tomorrow = _fixture_now(LIVE) + timedelta(days=1)
    res2 = run(transport=FixtureTransport(LIVE), now=tomorrow, data_dir=tmp_path / "data",
               feed_path=tmp_path / "feed.xml", mode="extractive")
    if res2.digest:
        ids1 = {i["id"] for s in first["sections"].values() for i in s}
        ids2 = {i["id"] for s in res2.digest["sections"].values() for i in s}
        assert not ids1 & ids2
    assert res.exit_code == EXIT_OK


def test_too_few_items_does_not_publish_and_keeps_previous(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "latest.json").write_text('{"previous": true}')
    res = run(transport=unit_transport, now=NOW, data_dir=data, feed_path=tmp_path / "feed.xml",
              sources=[UNIT_SOURCES["lab"], UNIT_SOURCES["rdf"]], mode="extractive")
    assert res.exit_code == EXIT_TOO_FEW
    assert json.loads((data / "latest.json").read_text()) == {"previous": True}
    assert not (tmp_path / "feed.xml").exists()
    health = json.loads((data / "health.json").read_text())
    assert health["status"] == "too-few-items" and health["failureReason"]


def test_validation_failure_does_not_publish(tmp_path, monkeypatch):
    import shipbrief.pipeline as pl
    monkeypatch.setattr(pl, "validate_digest", lambda d, now=None: ["forced failure"])
    res = _live_run(tmp_path)
    assert res.exit_code == EXIT_INVALID
    assert not (tmp_path / "data" / "latest.json").exists()
    assert json.loads((tmp_path / "data" / "health.json").read_text())["status"] == "failed-validation"


def test_all_sources_failing_is_handled(tmp_path):
    def dead(source, url):
        raise TimeoutError("down")
    res = run(transport=dead, now=NOW, data_dir=tmp_path / "data", feed_path=tmp_path / "feed.xml",
              mode="extractive")
    assert res.exit_code == EXIT_TOO_FEW
    assert all(not s["ok"] for s in res.health["sources"])


def test_archive_pruning_and_index(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    sample = json.loads((config.ROOT / "docs/samples/sample-digest.json").read_text())
    for d in (date(2026, 11, 9), date(2026, 11, 8), date(2026, 7, 1)):
        doc = dict(sample, date=d.isoformat())
        (data / f"{d.isoformat()}.json").write_text(json.dumps(doc))
    removed = publish.prune_archive(data, date(2026, 11, 9))
    assert removed == ["2026-07-01.json"]
    idx = publish.build_index(data)
    assert idx["latest"] == "2026-11-09" and [x["date"] for x in idx["days"]] == ["2026-11-09", "2026-11-08"]


def test_health_history_appends_runs(tmp_path):
    h = {"runId": "a", "date": "2026-11-09"}
    publish.write_health(h, tmp_path)
    publish.write_health({"runId": "b", "date": "2026-11-09"}, tmp_path)
    runs = json.loads((tmp_path / "health" / "2026-11-09.json").read_text())
    assert [r["runId"] for r in runs] == ["a", "b"]


def test_no_secret_in_outputs(tmp_path, monkeypatch):
    secret = "sk-ant-api03-THIS-IS-A-FAKE-SECRET-123456"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    _live_run(tmp_path)  # mode forced extractive; still must not leak env anywhere
    for p in tmp_path.rglob("*"):
        if p.is_file():
            assert secret not in p.read_text(errors="ignore")
