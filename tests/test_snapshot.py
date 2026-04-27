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

from src.snapshot import (
    MonotonicityViolation,
    check_monotonicity,
    compare_summaries,
    create_summary,
    load_snapshot,
    save_snapshot,
)

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


class TestMonotonicity:
    """Unit tests for cross-run monotonicity checks."""

    @staticmethod
    def _make_snapshot(
        *,
        record_count: int = 100,
        artifacts_sum: float = 500,
        badges_available_sum: float = 400,
        badges_functional_sum: float = 300,
        badges_reproducible_sum: float = 200,
        ae_memberships_sum: float = 150,
        names: list[str] | None = None,
        total_artifacts: int = 2000,
        total_conferences: int = 10,
    ) -> dict:
        """Build a minimal snapshot dict for monotonicity testing."""
        snap: dict = {
            "_version": 1,
            "files": {
                "assets/data/artifacts.json": {"record_count": record_count},
                "assets/data/ae_members.json": {"record_count": 50},
                "assets/data/combined_rankings.json": {
                    "record_count": record_count,
                    "numeric": {
                        "artifacts": {"sum": artifacts_sum},
                        "badges_available": {"sum": badges_available_sum},
                        "badges_functional": {"sum": badges_functional_sum},
                        "badges_reproducible": {"sum": badges_reproducible_sum},
                        "ae_memberships": {"sum": ae_memberships_sum},
                    },
                },
                "assets/data/search_data.json": {"record_count": record_count},
                "assets/data/institution_rankings.json": {"record_count": 30},
                "assets/data/top_repos.json": {"record_count": 20},
                "assets/data/summary.json": {
                    "key_count": 9,
                    "dict_numeric": {
                        "total_artifacts": total_artifacts,
                        "total_conferences": total_conferences,
                    },
                },
            },
        }
        if names is not None:
            snap["files"]["assets/data/combined_rankings.json"]["names"] = names
        return snap

    def test_no_violations_when_counts_increase(self):
        old = self._make_snapshot(record_count=100, artifacts_sum=500)
        new = self._make_snapshot(record_count=110, artifacts_sum=550)
        assert check_monotonicity(old, new) == []

    def test_no_violations_when_unchanged(self):
        snap = self._make_snapshot()
        assert check_monotonicity(snap, snap) == []

    def test_record_count_decrease_detected(self):
        old = self._make_snapshot(record_count=100)
        new = self._make_snapshot(record_count=95)
        violations = check_monotonicity(old, new)
        rc_violations = [v for v in violations if v.check == "record_count"]
        # artifacts.json, combined_rankings.json, search_data.json all have record_count=95
        assert len(rc_violations) >= 1
        assert any("decreased" in v.message for v in rc_violations)

    def test_artifacts_sum_decrease_detected(self):
        old = self._make_snapshot(artifacts_sum=500)
        new = self._make_snapshot(artifacts_sum=490)
        violations = check_monotonicity(old, new)
        assert any(v.check == "artifacts.sum" for v in violations)

    def test_badges_sum_decrease_detected(self):
        old = self._make_snapshot(badges_available_sum=400)
        new = self._make_snapshot(badges_available_sum=395)
        violations = check_monotonicity(old, new)
        assert any(v.check == "badges_available.sum" for v in violations)

    def test_ae_memberships_decrease_detected(self):
        old = self._make_snapshot(ae_memberships_sum=150)
        new = self._make_snapshot(ae_memberships_sum=140)
        violations = check_monotonicity(old, new)
        assert any(v.check == "ae_memberships.sum" for v in violations)

    def test_name_vanished_detected(self):
        old = self._make_snapshot(names=["Alice", "Bob", "Charlie"])
        new = self._make_snapshot(names=["Alice", "Charlie"])
        violations = check_monotonicity(old, new)
        assert any(v.check == "names" and "Bob" in v.message for v in violations)

    def test_name_added_is_fine(self):
        old = self._make_snapshot(names=["Alice", "Bob"])
        new = self._make_snapshot(names=["Alice", "Bob", "Charlie"])
        violations = check_monotonicity(old, new)
        name_violations = [v for v in violations if v.check == "names"]
        assert name_violations == []

    def test_total_artifacts_decrease_detected(self):
        old = self._make_snapshot(total_artifacts=2000)
        new = self._make_snapshot(total_artifacts=1990)
        violations = check_monotonicity(old, new)
        assert any(v.check == "total_artifacts" for v in violations)

    def test_total_conferences_decrease_detected(self):
        old = self._make_snapshot(total_conferences=10)
        new = self._make_snapshot(total_conferences=9)
        violations = check_monotonicity(old, new)
        assert any(v.check == "total_conferences" for v in violations)

    def test_missing_reference_file_no_crash(self):
        """If the old snapshot doesn't have a file, skip it gracefully."""
        old: dict = {"_version": 1, "files": {}}
        new = self._make_snapshot()
        # Should not raise
        violations = check_monotonicity(old, new)
        assert violations == []

    def test_missing_new_file_no_crash(self):
        """If the new snapshot doesn't have a file, skip it gracefully."""
        old = self._make_snapshot()
        new: dict = {"_version": 1, "files": {}}
        # record_count checks: old has values, new has None → no violation (None guard)
        violations = check_monotonicity(old, new)
        assert violations == []

    def test_violation_str_format(self):
        v = MonotonicityViolation("file.json", "record_count", "decreased from 100 to 90")
        assert "[ERROR]" in str(v)
        assert "file.json" in str(v)
        assert "decreased" in str(v)
