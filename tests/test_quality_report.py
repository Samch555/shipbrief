import importlib.util
import json
from datetime import date

from shipbrief import config
from tests.test_publish import _live_run

spec = importlib.util.spec_from_file_location("qr", config.ROOT / "scripts" / "quality_report.py")
qr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qr)


def test_report_from_real_run(tmp_path):
    _live_run(tmp_path)
    # add a failed run on another day with a flaky source and LLM cost
    (tmp_path / "data" / "health" / "2026-11-08.json").write_text(json.dumps([{
        "runId": "x", "date": "2026-11-08", "trigger": "schedule", "startedAt": "2026-11-08T11:40:00Z", "durationSeconds": 30,
        "status": "too-few-items", "sources": [{"id": "openai-news", "ok": False, "items": 0, "error": "HTTPError 503"}],
        "llm": {"estimatedCostUsd": 0.0123, "inputTokens": 1000, "outputTokens": 100, "budgetExhausted": True},
        "factCheck": {"summariesRejected": 2, "provenanceRejected": 0}}]))
    log = tmp_path / "REVIEW_LOG.md"
    log.write_text((config.ROOT / "REVIEW_LOG.md").read_text() + "\n### 2026-11-09\n- **Read it?** yes\n")
    report = qr.build_report(tmp_path / "data", date(2026, 10, 27), date(2026, 11, 9), log)
    assert "1 / 14" in report
    assert "`openai-news`" in report and "HTTPError 503" in report
    assert "$0.0123" in report
    assert "| REVIEW_LOG.md days filled in | 1 |" in report
    assert "median 33 min" in report
