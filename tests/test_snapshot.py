"""Snapshot tests for pipeline output stability.

These tests compare current pipeline output against a committed reference
snapshot.  When a PR intentionally changes scores or record counts, the
developer updates the snapshot with::

    python -m src.snapshot --output_dir output/staging --update

and commits the new ``tests/snapshots/pipeline_snapshot.json``.  The PR
diff then shows exactly what changed, making review trivial.

If no reference snapshot exists yet, the test is skipped with instructions
to create one.
"""

import json
from pathlib import Path

import pytest

from src.snapshot import compare_summaries, create_summary, load_snapshot, save_snapshot

SNAPSHOT_DIR = Path("tests/snapshots")
SNAPSHOT_FILE = SNAPSHOT_DIR / "pipeline_snapshot.json"

# Pipeline output directories to try (in priority order)
_OUTPUT_CANDIDATES = [
    Path("output/staging"),
    Path("../reprodb.github.io"),
]


def _find_output_dir() -> Path | None:
    for d in _OUTPUT_CANDIDATES:
        if (d / "assets" / "data").is_dir():
            return d
    return None


class TestSnapshotSummary:
    """Unit-level tests for snapshot creation and comparison."""

    def test_create_summary_returns_version(self, tmp_path):
        (tmp_path / "assets" / "data").mkdir(parents=True)
        (tmp_path / "assets" / "data" / "test.json").write_text('[{"a":1}]')
        summary = create_summary(tmp_path)
        assert summary["_version"] == 1
        assert "assets/data/test.json" in summary["files"]

    def test_create_summary_record_count(self, tmp_path):
        (tmp_path / "assets" / "data").mkdir(parents=True)
        records = [{"name": "Alice", "score": 10}, {"name": "Bob", "score": 20}]
        (tmp_path / "assets" / "data" / "test.json").write_text(json.dumps(records))
        summary = create_summary(tmp_path)
        assert summary["files"]["assets/data/test.json"]["record_count"] == 2

    def test_identical_summaries_produce_no_diffs(self, tmp_path):
        (tmp_path / "assets" / "data").mkdir(parents=True)
        (tmp_path / "assets" / "data" / "a.json").write_text('[{"x":1}]')
        s = create_summary(tmp_path)
        assert compare_summaries(s, s) == []

    def test_record_count_change_detected(self, tmp_path):
        (tmp_path / "assets" / "data").mkdir(parents=True)
        (tmp_path / "assets" / "data" / "a.json").write_text('[{"x":1}]')
        old = create_summary(tmp_path)

        (tmp_path / "assets" / "data" / "a.json").write_text('[{"x":1},{"x":2}]')
        new = create_summary(tmp_path)

        diffs = compare_summaries(old, new)
        assert any("record_count" in d for d in diffs)

    def test_numeric_stats_change_detected(self, tmp_path):
        (tmp_path / "assets" / "data").mkdir(parents=True)
        data1 = [{"combined_score": 10}, {"combined_score": 20}]
        data2 = [{"combined_score": 10}, {"combined_score": 30}]

        (tmp_path / "assets" / "data" / "a.json").write_text(json.dumps(data1))
        old = create_summary(tmp_path)

        (tmp_path / "assets" / "data" / "a.json").write_text(json.dumps(data2))
        new = create_summary(tmp_path)

        diffs = compare_summaries(old, new)
        assert any("combined_score" in d for d in diffs)

    def test_new_file_detected(self, tmp_path):
        (tmp_path / "assets" / "data").mkdir(parents=True)
        (tmp_path / "assets" / "data" / "a.json").write_text("[]")
        old = create_summary(tmp_path)

        (tmp_path / "assets" / "data" / "b.json").write_text("[]")
        new = create_summary(tmp_path)

        diffs = compare_summaries(old, new)
        assert any("NEW" in d for d in diffs)

    def test_removed_file_detected(self, tmp_path):
        (tmp_path / "assets" / "data").mkdir(parents=True)
        (tmp_path / "assets" / "data" / "a.json").write_text("[]")
        (tmp_path / "assets" / "data" / "b.json").write_text("[]")
        old = create_summary(tmp_path)

        (tmp_path / "assets" / "data" / "b.json").unlink()
        new = create_summary(tmp_path)

        diffs = compare_summaries(old, new)
        assert any("REMOVED" in d for d in diffs)

    def test_save_and_load_roundtrip(self, tmp_path):
        snapshot = {"_version": 1, "files": {"a.json": {"record_count": 42}}}
        path = tmp_path / "snap.json"
        save_snapshot(snapshot, path)
        loaded = load_snapshot(path)
        assert loaded == snapshot


@pytest.mark.integration
class TestSnapshotAgainstReference:
    """Compare live pipeline output against the committed reference snapshot.

    This test class is the one that lights up in CI / PR reviews.
    """

    def test_output_matches_snapshot(self):
        output_dir = _find_output_dir()
        if output_dir is None:
            pytest.skip("No pipeline output directory found — run the pipeline first")

        reference = load_snapshot()
        if reference is None:
            pytest.skip(
                f"No reference snapshot at {SNAPSHOT_FILE} — "
                "create one with: python -m src.snapshot --output_dir output/staging --update"
            )

        current = create_summary(output_dir)
        diffs = compare_summaries(reference, current)

        if diffs:
            msg = f"Pipeline output differs from snapshot ({len(diffs)} changes):\n"
            msg += "\n".join(f"  {d}" for d in diffs)
            msg += "\n\nTo accept these changes: python -m src.snapshot --output_dir " + str(output_dir) + " --update"
            pytest.fail(msg)
