"""Tests for src.cache — content-hash skip cache."""

from __future__ import annotations

import os
import time

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


def test_ttl_none_never_expires(tmp_path):
    """Default ttl=None means the cache never expires by time alone."""
    (tmp_path / "input.txt").write_text("data")
    (tmp_path / "output.txt").write_text("result")
    stage = _stage_for(tmp_path)
    cache.mark_done(stage, tmp_path)
    # Backdate the cache file by 365 days — still valid without TTL.
    cf = cache._cache_file(stage, tmp_path)
    old_time = time.time() - 365 * 86400
    os.utime(cf, (old_time, old_time))
    assert cache.should_skip(stage, tmp_path) is True


def test_ttl_fresh_cache_skips(tmp_path):
    """A cache entry younger than TTL allows skipping."""
    (tmp_path / "input.txt").write_text("data")
    (tmp_path / "output.txt").write_text("result")
    stage = Stage(
        name="dummy",
        module="src.cache",
        description="test",
        inputs=("input.txt",),
        outputs=("output.txt",),
        ttl=3600,
    )
    cache.mark_done(stage, tmp_path)
    assert cache.should_skip(stage, tmp_path) is True


def test_ttl_expired_cache_reruns(tmp_path):
    """A cache entry older than TTL forces a re-run."""
    (tmp_path / "input.txt").write_text("data")
    (tmp_path / "output.txt").write_text("result")
    stage = Stage(
        name="dummy",
        module="src.cache",
        description="test",
        inputs=("input.txt",),
        outputs=("output.txt",),
        ttl=3600,
    )
    cache.mark_done(stage, tmp_path)
    # Backdate the cache file beyond the 1-hour TTL.
    cf = cache._cache_file(stage, tmp_path)
    old_time = time.time() - 7200  # 2 hours ago
    os.utime(cf, (old_time, old_time))
    assert cache.should_skip(stage, tmp_path) is False
