"""Tests for src.cache — content-hash skip cache."""

from __future__ import annotations

from src import cache
from src.stages import Stage


def _stage_for(tmp_path) -> Stage:
    return Stage(
        name="dummy",
        module="src.cache",  # any importable module with a real source file
        description="test",
        inputs=("input.txt",),
        outputs=("output.txt",),
    )


def test_no_inputs_means_no_skip(tmp_path):
    stage = Stage(name="x", module="src.cache", description="", outputs=("o",))
    assert cache.should_skip(stage, tmp_path) is False


def test_first_run_not_skipped(tmp_path):
    (tmp_path / "input.txt").write_text("data")
    (tmp_path / "output.txt").write_text("result")
    stage = _stage_for(tmp_path)
    assert cache.should_skip(stage, tmp_path) is False


def test_skip_when_inputs_unchanged(tmp_path):
    (tmp_path / "input.txt").write_text("data")
    (tmp_path / "output.txt").write_text("result")
    stage = _stage_for(tmp_path)
    cache.mark_done(stage, tmp_path)
    assert cache.should_skip(stage, tmp_path) is True


def test_no_skip_when_input_changes(tmp_path):
    (tmp_path / "input.txt").write_text("data")
    (tmp_path / "output.txt").write_text("result")
    stage = _stage_for(tmp_path)
    cache.mark_done(stage, tmp_path)
    (tmp_path / "input.txt").write_text("changed")
    assert cache.should_skip(stage, tmp_path) is False


def test_no_skip_when_output_missing(tmp_path):
    (tmp_path / "input.txt").write_text("data")
    (tmp_path / "output.txt").write_text("result")
    stage = _stage_for(tmp_path)
    cache.mark_done(stage, tmp_path)
    (tmp_path / "output.txt").unlink()
    assert cache.should_skip(stage, tmp_path) is False


def test_no_skip_when_input_missing(tmp_path):
    (tmp_path / "input.txt").write_text("data")
    (tmp_path / "output.txt").write_text("result")
    stage = _stage_for(tmp_path)
    cache.mark_done(stage, tmp_path)
    (tmp_path / "input.txt").unlink()
    assert cache.should_skip(stage, tmp_path) is False


def test_invalidate_forces_rerun(tmp_path):
    (tmp_path / "input.txt").write_text("data")
    (tmp_path / "output.txt").write_text("result")
    stage = _stage_for(tmp_path)
    cache.mark_done(stage, tmp_path)
    assert cache.should_skip(stage, tmp_path) is True
    cache.invalidate(stage, tmp_path)
    assert cache.should_skip(stage, tmp_path) is False
