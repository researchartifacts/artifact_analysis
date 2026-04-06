#!/usr/bin/env python3
"""
Maintain ranking history snapshots for authors and institutions.

Each pipeline run appends a timestamped snapshot to:
  - assets/data/ranking_history.json       (author rankings over time)
  - assets/data/institution_ranking_history.json  (institution rankings over time)

The history files are arrays of snapshot objects:
  [
    {
      "date": "2026-03",
      "entries": {
        "Author Name": {"rank": 1, "score": 60, "as": 0, "aes": 60},
        ...
      }
    },
    ...
  ]

Only authors/institutions that appear in the current rankings are tracked.
The "date" is year-month (YYYY-MM) to give monthly granularity.

Usage:
  python -m src.generators.generate_ranking_history --data_dir ../researchartifacts.github.io
"""

import argparse
import json
import os
from datetime import datetime


def _load_json(path: str) -> list | dict:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


def _snapshot_date() -> str:
    """Return current year-month string."""
    return datetime.now().strftime("%Y-%m")


def _has_snapshot(history: list, date: str) -> bool:
    """Check if a snapshot for the given date already exists."""
    return any(snap["date"] == date for snap in history)


def _update_history(history: list, current_entries: dict, date: str) -> list:
    """Add or replace a snapshot for the given date."""
    # Remove existing snapshot for this date if present (for --force)
    history = [snap for snap in history if snap["date"] != date]
    history.append({"date": date, "entries": current_entries})
    # Sort chronologically
    history.sort(key=lambda s: s["date"])
    return history


def generate_ranking_history(data_dir: str, force: bool = False) -> None:
    """Generate/update author and institution ranking history."""
    date = _snapshot_date()

    # ── Author rankings ──────────────────────────────────────────────────
    cr_path = os.path.join(data_dir, "assets/data/combined_rankings.json")
    author_hist_path = os.path.join(data_dir, "assets/data/ranking_history.json")

    rankings = _load_json(cr_path)
    author_history: list = _load_json(author_hist_path)  # type: ignore[assignment]

    if _has_snapshot(author_history, date) and not force:
        print(f"  Author ranking history: snapshot for {date} already exists, skipping (use --force to overwrite)")
    else:
        author_entries = {}
        for r in rankings:
            name = r.get("name", "")
            if not name:
                continue
            author_entries[name] = {
                "rank": r.get("rank", 0),
                "score": r.get("combined_score", 0),
                "as": r.get("artifact_score", 0),
                "aes": r.get("ae_score", 0),
                "tp": r.get("total_papers", 0),
                "ta": r.get("artifacts", 0),
                "ar": r.get("artifact_rate", 0),
                "rr": r.get("repro_rate", 0),
            }

        author_history = _update_history(author_history, author_entries, date)

        with open(author_hist_path, "w") as f:
            json.dump(author_history, f, ensure_ascii=False, separators=(",", ":"))

        print(f"  Author ranking history: {len(author_history)} snapshots, {len(author_entries)} entries for {date}")
        print(f"  Wrote {author_hist_path} ({os.path.getsize(author_hist_path) / 1024:.0f}KB)")

    # ── Institution rankings ─────────────────────────────────────────────
    ir_path = os.path.join(data_dir, "assets/data/institution_rankings.json")
    inst_hist_path = os.path.join(data_dir, "assets/data/institution_ranking_history.json")

    inst_rankings = _load_json(ir_path)
    inst_history: list = _load_json(inst_hist_path)  # type: ignore[assignment]

    if _has_snapshot(inst_history, date) and not force:
        print(f"  Institution ranking history: snapshot for {date} already exists, skipping (use --force to overwrite)")
    else:
        inst_entries = {}
        for idx, r in enumerate(inst_rankings):
            name = r.get("affiliation", "")
            if not name:
                continue
            # Calculate repro rate for institution
            inst_rr = 0
            if r.get("artifacts", 0) > 0:
                inst_rr = round((r.get("badges_reproducible", 0) / r["artifacts"]) * 100, 1)
            inst_entries[name] = {
                "rank": idx + 1,
                "score": r.get("combined_score", 0),
                "as": r.get("artifact_score", 0),
                "aes": r.get("ae_score", 0),
                "tp": r.get("total_papers", 0),
                "ta": r.get("artifacts", 0),
                "ar": r.get("artifact_rate", 0),
                "rr": inst_rr,
                "r": r.get("num_authors", 0),
            }

        inst_history = _update_history(inst_history, inst_entries, date)

        with open(inst_hist_path, "w") as f:
            json.dump(inst_history, f, ensure_ascii=False, separators=(",", ":"))

        print(f"  Institution ranking history: {len(inst_history)} snapshots, {len(inst_entries)} entries for {date}")
        print(f"  Wrote {inst_hist_path} ({os.path.getsize(inst_hist_path) / 1024:.0f}KB)")


def main():
    parser = argparse.ArgumentParser(description="Generate/update ranking history snapshots")
    parser.add_argument("--data_dir", type=str, required=True, help="Path to the researchartifacts.github.io directory")
    parser.add_argument("--force", action="store_true", help="Overwrite existing snapshot for the current month")
    args = parser.parse_args()
    generate_ranking_history(args.data_dir, force=args.force)


if __name__ == "__main__":
    main()
