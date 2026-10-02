"""Shape checks for recorded fixtures; skipped until some are recorded."""

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
DIRS = sorted(p for p in FIXTURES.iterdir() if p.is_dir())


@pytest.mark.skipif(not DIRS, reason="no fixtures recorded yet")
@pytest.mark.parametrize("fixture", DIRS, ids=lambda p: p.name)
def test_fixture_is_complete(fixture):
    meta = json.loads((fixture / "meta.json").read_text())
    json.loads((fixture / "query.json").read_text())
    json.loads((fixture / "create_task.json").read_text())
    polls = (fixture / "fetch_result.jsonl").read_text().splitlines()
    assert len(polls) == meta["polls"] > 0
    assert meta["task_id"] == "<scrubbed>" or meta["task_id"]
