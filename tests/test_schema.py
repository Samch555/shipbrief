import copy
import json
from datetime import datetime, timezone

import pytest

from shipbrief import config
from shipbrief.validate import validate_digest

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def sample():
    return json.loads((config.ROOT / "docs/samples/sample-digest.json").read_text())


def test_sample_is_valid(sample):
    assert validate_digest(sample, now=NOW) == []


def test_missing_schema_version_fails(sample):
    del sample["schemaVersion"]
    assert any("schemaVersion" in e for e in validate_digest(sample, now=NOW))


def test_major_version_2_rejected(sample):
    sample["schemaVersion"] = "2.0.0"
    assert validate_digest(sample, now=NOW)


def test_item_without_url_fails(sample):
    del sample["sections"]["topStories"][0]["url"]
    assert validate_digest(sample, now=NOW)


def test_non_http_url_fails(sample):
    sample["sections"]["topStories"][0]["url"] = "javascript:alert(1)"
    assert validate_digest(sample, now=NOW)


def test_unknown_field_rejected(sample):
    sample["sections"]["topStories"][0]["body"] = "full article text"
    assert validate_digest(sample, now=NOW)


def test_tool_item_requires_what_and_who(sample):
    del sample["sections"]["tools"][0]["whoItsFor"]
    assert validate_digest(sample, now=NOW)


def test_future_published_at_rejected(sample):
    sample["sections"]["research"][0]["publishedAt"] = "2027-01-01T00:00:00Z"
    errs = validate_digest(sample, now=NOW)
    assert any("future" in e for e in errs)


def test_prompt_word_limit(sample):
    sample["promptOfTheDay"]["prompt"] = "word " * 151
    s = copy.deepcopy(sample)
    s["promptOfTheDay"]["prompt"] = s["promptOfTheDay"]["prompt"][:1200]
    errs = validate_digest(s, now=NOW)
    assert any("words" in e for e in errs)


def test_based_on_must_reference_item(sample):
    sample["promptOfTheDay"]["basedOn"]["itemId"] = "0" * 16
    assert any("basedOn" in e for e in validate_digest(sample, now=NOW))


def test_generated_by_values(sample):
    sample["sections"]["topStories"][0]["generatedBy"] = "gpt-x"
    assert validate_digest(sample, now=NOW)
    sample["sections"]["topStories"][0]["generatedBy"] = "claude-haiku-5-5"
    assert validate_digest(sample, now=NOW) == []


def test_too_few_top_stories(sample):
    sample["sections"]["topStories"] = sample["sections"]["topStories"][:2]
    assert any("topStories" in e for e in validate_digest(sample, now=NOW))
