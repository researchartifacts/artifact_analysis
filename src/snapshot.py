"""Snapshot summaries for pipeline output stability verification.

A "snapshot" is a compact JSON file that records deterministic statistics
about every pipeline output: record counts, numeric field ranges, score
sums, and SHA-256 checksums of the serialised data.  Two snapshots taken
from the same code + same input should be identical.

Usage::

    # Create / update the reference snapshot
    python -m src.snapshot --output_dir output/staging --update

    # Compare current output against the saved snapshot (exit 1 on diff)
    python -m src.snapshot --output_dir output/staging

The reference snapshot lives at ``tests/snapshots/pipeline_snapshot.json``.
It is committed to the repo so that every PR shows exactly which numbers
changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

SNAPSHOT_PATH = Path("tests/snapshots/pipeline_snapshot.json")


# ── Helpers ──────────────────────────────────────────────────────────────────


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(obj: object) -> bytes:
    """Deterministic JSON bytes (sorted keys, no trailing whitespace)."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def _numeric_stats(records: list[dict], field: str) -> dict | None:
    """Return min/max/sum/mean for a numeric field, or None if not present."""
    vals = [r[field] for r in records if field in r and isinstance(r[field], (int, float))]
    if not vals:
        return None
    return {
        "min": min(vals),
        "max": max(vals),
        "sum": round(sum(vals), 4),
        "mean": round(sum(vals) / len(vals), 4),
        "count": len(vals),
    }


def _summarise_json(path: Path) -> dict:
    """Build a summary dict for one JSON output file."""
    raw = path.read_bytes()
    data = json.loads(raw)
    summary: dict = {
        "sha256": _sha256(_canonical_json(data)),
        "size_bytes": len(raw),
    }
    if isinstance(data, list):
        summary["record_count"] = len(data)
        if data and isinstance(data[0], dict):
            summary["fields"] = sorted(data[0].keys())
            # Numeric field stats for key ranking/score fields
            for field in (
                "combined_score",
                "artifact_score",
                "ae_score",
                "artifacts",
                "ae_memberships",
                "total_papers",
                "artifact_rate",
                "repro_rate",
                "badges_available",
                "badges_functional",
                "badges_reproducible",
                "citation_score",
                "artifact_citations",
                "total_score",
                "total_artifacts",
                "total_ae_memberships",
            ):
                stats = _numeric_stats(data, field)
                if stats:
                    summary.setdefault("numeric", {})[field] = stats
    elif isinstance(data, dict):
        summary["key_count"] = len(data)
    return summary


def _summarise_yaml(path: Path) -> dict:
    """Build a summary dict for one YAML output file."""
    raw = path.read_bytes()
    data = yaml.safe_load(raw)
    summary: dict = {
        "sha256": _sha256(raw),
        "size_bytes": len(raw),
    }
    if isinstance(data, list):
        summary["record_count"] = len(data)
    elif isinstance(data, dict):
        summary["key_count"] = len(data)
    return summary


# ── Public API ───────────────────────────────────────────────────────────────


def create_summary(output_dir: Path) -> dict:
    """Scan pipeline output and return a snapshot summary dict.

    The dict maps ``relative_path -> {sha256, record_count, ...}``.
    """
    summary: dict = {"_version": 1, "files": {}}

    # JSON files in assets/data/
    json_dir = output_dir / "assets" / "data"
    if json_dir.is_dir():
        for f in sorted(json_dir.glob("*.json")):
            key = f"assets/data/{f.name}"
            try:
                summary["files"][key] = _summarise_json(f)
            except Exception as exc:
                logger.warning("Failed to summarise %s: %s", key, exc)

    # YAML files in _data/
    yaml_dir = output_dir / "_data"
    if yaml_dir.is_dir():
        for f in sorted(yaml_dir.glob("*.yml")):
            key = f"_data/{f.name}"
            try:
                summary["files"][key] = _summarise_yaml(f)
            except Exception as exc:
                logger.warning("Failed to summarise %s: %s", key, exc)

    # Chart SVGs — just count + total size (content-level diffing not useful)
    charts_dir = output_dir / "assets" / "charts"
    if charts_dir.is_dir():
        svgs = sorted(charts_dir.glob("*.svg"))
        summary["files"]["assets/charts/"] = {
            "chart_count": len(svgs),
            "total_bytes": sum(f.stat().st_size for f in svgs),
        }

    return summary


def compare_summaries(old: dict, new: dict) -> list[str]:
    """Compare two snapshot dicts and return a list of human-readable diffs.

    Returns an empty list if the snapshots are identical.
    """
    diffs: list[str] = []
    old_files = old.get("files", {})
    new_files = new.get("files", {})

    all_keys = sorted(set(old_files) | set(new_files))
    for key in all_keys:
        if key not in old_files:
            diffs.append(f"+ {key}: NEW file (not in reference snapshot)")
            continue
        if key not in new_files:
            diffs.append(f"- {key}: REMOVED (was in reference snapshot)")
            continue

        o, n = old_files[key], new_files[key]

        # Record count changes
        for count_field in ("record_count", "key_count", "chart_count"):
            ov = o.get(count_field)
            nv = n.get(count_field)
            if ov is not None and nv is not None and ov != nv:
                delta = nv - ov
                sign = "+" if delta > 0 else ""
                diffs.append(f"  {key}: {count_field} {ov} → {nv} ({sign}{delta})")

        # Numeric field changes (scores, rates)
        o_num = o.get("numeric", {})
        n_num = n.get("numeric", {})
        for field in sorted(set(o_num) | set(n_num)):
            os_ = o_num.get(field, {})
            ns_ = n_num.get(field, {})
            for stat in ("sum", "min", "max", "mean", "count"):
                ov = os_.get(stat)
                nv = ns_.get(stat)
                if ov is not None and nv is not None and ov != nv:
                    diffs.append(f"  {key}: {field}.{stat} {ov} → {nv}")

        # Content hash change (catch-all: if sha256 changed but nothing above triggered)
        if o.get("sha256") and n.get("sha256") and o["sha256"] != n["sha256"]:
            # Only flag if we haven't already listed specific changes for this file
            prefix = f"  {key}: "
            file_specific = [d for d in diffs if d.startswith(prefix)]
            if not file_specific:
                diffs.append(f"  {key}: content changed (sha256 differs)")

    return diffs


def save_snapshot(summary: dict, path: Path | None = None) -> Path:
    """Write a snapshot summary to disk."""
    path = path or SNAPSHOT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    logger.info("Snapshot saved to %s", path)
    return path


def load_snapshot(path: Path | None = None) -> dict | None:
    """Load a snapshot from disk, or None if it doesn't exist."""
    path = path or SNAPSHOT_PATH
    if not path.is_file():
        return None
    return json.loads(path.read_text())


# ── CLI ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline output snapshot tool")
    parser.add_argument("--output_dir", required=True, help="Pipeline output directory")
    parser.add_argument("--update", action="store_true", help="Update the reference snapshot")
    parser.add_argument("--snapshot", type=str, default=None, help="Custom snapshot path")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    output_dir = Path(args.output_dir)
    snap_path = Path(args.snapshot) if args.snapshot else SNAPSHOT_PATH

    current = create_summary(output_dir)
    file_count = len(current.get("files", {}))
    logger.info("Scanned %d output files in %s", file_count, output_dir)

    if args.update:
        save_snapshot(current, snap_path)
        sys.exit(0)

    reference = load_snapshot(snap_path)
    if reference is None:
        logger.error("No reference snapshot at %s — run with --update first", snap_path)
        sys.exit(1)

    diffs = compare_summaries(reference, current)
    if not diffs:
        logger.info("✓ Output matches reference snapshot (%d files)", file_count)
        sys.exit(0)

    logger.error("✗ Output differs from reference snapshot:")
    for d in diffs:
        logger.error("  %s", d)
    sys.exit(1)


if __name__ == "__main__":
    main()
