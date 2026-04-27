"""Run metadata — records provenance for each pipeline execution.

Writes ``output_dir/_build/run_metadata.json`` with git revisions,
timestamps, input hashes, and stage timings.  This file is committed
to ``reprodb-pipeline-results`` by :func:`src.save_results.save_results` so every
historical run is traceable.

Usage::

    from src.run_metadata import write_run_metadata
    write_run_metadata(output_dir, timings={"statistics": 1.2, ...})
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def _git_info(repo_dir: Path) -> dict:
    """Collect git revision info for a repository."""
    info: dict = {}
    try:
        info["commit"] = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=repo_dir, timeout=5,
        ).stdout.strip() or "unknown"
        info["branch"] = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=repo_dir, timeout=5,
        ).stdout.strip() or "unknown"
        info["dirty"] = subprocess.run(
            ["git", "diff", "--quiet"],
            capture_output=True, cwd=repo_dir, timeout=5,
        ).returncode != 0
    except (subprocess.TimeoutExpired, OSError):
        info["commit"] = "unknown"
        info["branch"] = "unknown"
        info["dirty"] = None
    return info


def _file_hash(path: Path) -> str | None:
    """SHA-256 of a file, or None if it doesn't exist."""
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_run_metadata(
    output_dir: Path,
    *,
    timings: dict[str, float] | None = None,
    pipeline_dir: Path | None = None,
    dblp_file: Path | None = None,
) -> Path:
    """Write run metadata JSON to ``output_dir/_build/run_metadata.json``.

    Returns the path to the written file.
    """
    pipeline_dir = pipeline_dir or Path(".")
    metadata: dict = {
        "schema_version": 1,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "pipeline": _git_info(pipeline_dir),
    }

    # Website repo info (if output is the website)
    website_dir = Path("../reprodb.github.io")
    if website_dir.is_dir() and (website_dir / ".git").exists():
        metadata["website"] = _git_info(website_dir)

    # Input hashes
    inputs: dict = {}
    if dblp_file and dblp_file.is_file():
        inputs["dblp_sha256"] = _file_hash(dblp_file)
    # Hash the scraper input files
    for yml in sorted((output_dir / "_data").glob("*.yml")) if (output_dir / "_data").is_dir() else []:
        inputs[f"_data/{yml.name}"] = _file_hash(yml)
    if inputs:
        metadata["input_hashes"] = inputs

    # Stage timings
    if timings:
        metadata["stage_timings"] = {
            k: round(v, 2) for k, v in sorted(timings.items(), key=lambda x: -x[1])
        }
        metadata["total_elapsed"] = round(sum(timings.values()), 2)

    # Python version
    import sys
    metadata["python_version"] = sys.version.split()[0]

    # Environment hints
    metadata["env"] = {
        "github_actions": os.environ.get("GITHUB_ACTIONS") == "true",
        "ci": os.environ.get("CI") == "true",
    }

    # Write
    out_path = output_dir / "_build" / "run_metadata.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(metadata, indent=2, sort_keys=False) + "\n")
    logger.info("Run metadata written to %s", out_path)
    return out_path
