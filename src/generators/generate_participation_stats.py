#!/usr/bin/env python3
"""
Generate AE participation statistics using the local DBLP XML file.

For each conference/year in the pipeline's artifacts data, this script:
1. Parses the DBLP XML to count ALL papers published at that venue/year.
2. Computes AE participation rate (ae_papers / total_papers).
3. Computes badge rates as % of all papers (not just AE papers).

Requires: data/dblp/dblp.xml.gz (downloaded by scripts/download_dblp.sh)

Writes:
  _data/participation_stats.yml     — per-conference/year participation data
  assets/data/participation_stats.json — same data in JSON

Usage:
  python -m src.generators.generate_participation_stats \
      --dblp_file data/dblp/dblp.xml.gz \
      --output_dir ../researchartifacts.github.io
"""

import argparse
import json
import os
import re
import yaml
from collections import defaultdict
from gzip import GzipFile

import lxml.etree as ET

from .generate_author_stats import venue_to_conference

AREA_MAP = {
    "USENIXSEC": "security", "NDSS": "security", "ACSAC": "security",
    "PETS": "security", "CHES": "security", "WOOT": "security",
    "OSDI": "systems", "SOSP": "systems", "ATC": "systems",
    "EUROSYS": "systems", "FAST": "systems", "SC": "systems",
    "SYSTEX": "security",
}


def _count_papers_from_dblp(dblp_file, target_conf_years):
    """Parse DBLP XML and count papers per (conference, year).

    Args:
        dblp_file: Path to dblp.xml.gz
        target_conf_years: set of (conf_upper, year_int) tuples to count

    Returns:
        dict: (conf, year) -> paper_count
    """
    # Build set of conferences we care about for early filtering
    target_confs = {cy[0] for cy in target_conf_years}

    counts = defaultdict(int)  # (conf, year) -> count
    print(f"Parsing DBLP XML for paper counts ({len(target_conf_years)} conference/year targets)...")

    dblp_stream = GzipFile(filename=dblp_file)
    iteration = 0

    for _, elem in ET.iterparse(
        dblp_stream,
        events=("end",),
        tag=("inproceedings", "article"),
        load_dtd=True,
        recover=True,
        huge_tree=True,
    ):
        booktitle = elem.findtext("booktitle") or elem.findtext("journal") or ""
        mapped_conf = venue_to_conference(booktitle)
        if mapped_conf and mapped_conf in target_confs:
            year_str = elem.findtext("year")
            if year_str:
                year = int(year_str)
                if (mapped_conf, year) in target_conf_years:
                    counts[(mapped_conf, year)] += 1

        iteration += 1
        if iteration % 2_000_000 == 0:
            print(f"  ... {iteration // 1_000_000}M elements processed")
        elem.clear()

    dblp_stream.close()
    print(f"  Done — {iteration} elements, found counts for {len(counts)} conference/years")
    return dict(counts)


def generate_participation_stats(dblp_file, output_dir):
    """Generate AE participation and badge-rate statistics."""

    if not os.path.exists(dblp_file):
        print(f"Error: DBLP file not found: {dblp_file}")
        print("  Run scripts/download_dblp.sh first.")
        return

    # Load artifacts_by_conference for per-conference badge counts
    abc_path = os.path.join(output_dir, "_data/artifacts_by_conference.yml")
    if not os.path.exists(abc_path):
        print(f"Error: {abc_path} not found — run generate_statistics first")
        return

    with open(abc_path) as f:
        by_conference = yaml.safe_load(f)

    # Build per-conference/year AE counts and badge counts from pipeline data
    ae_data = {}  # (conf, year) -> {ae_papers, available, functional, ...}
    for conf in by_conference:
        name = conf["name"]
        for yd in conf["years"]:
            key = (name, yd["year"])
            ae_data[key] = {
                "ae_papers": yd["total"],
                "available": yd.get("available", 0),
                "functional": yd.get("functional", 0),
                "reproduced": yd.get("reproducible", 0),
                "category": conf["category"],
                "venue_type": conf.get("venue_type", "conference"),
            }

    # Parse DBLP XML for total paper counts
    dblp_counts = _count_papers_from_dblp(dblp_file, set(ae_data.keys()))

    # Build stats entries
    stats = []
    for (conf, year), info in sorted(ae_data.items()):
        total_papers = dblp_counts.get((conf, year))
        if not total_papers:
            print(f"  ⚠ {conf} {year}: no DBLP data")
            continue

        ae_papers = info["ae_papers"]
        participation_rate = round(ae_papers / total_papers * 100, 1)
        area = AREA_MAP.get(conf, "unknown")

        entry = {
            "conference": conf,
            "year": year,
            "category": area,
            "venue_type": info["venue_type"],
            "total_papers": total_papers,
            "ae_papers": ae_papers,
            "participation_pct": participation_rate,
            "available": info["available"],
            "functional": info["functional"],
            "reproduced": info["reproduced"],
            "available_pct": round(info["available"] / total_papers * 100, 1),
            "functional_pct": round(info["functional"] / total_papers * 100, 1),
            "reproduced_pct": round(info["reproduced"] / total_papers * 100, 1),
        }
        stats.append(entry)
        print(f"  {conf} {year}: {ae_papers}/{total_papers} = {participation_rate}% AE participation")

    if not stats:
        print("No participation data generated")
        return

    # Sort by conference then year
    stats.sort(key=lambda x: (x["conference"], x["year"]))

    # Compute area-level summaries
    area_year = defaultdict(lambda: defaultdict(lambda: {"ae": 0, "total": 0,
        "avail": 0, "func": 0, "repro": 0}))
    for s in stats:
        ay = area_year[s["category"]][s["year"]]
        ay["ae"] += s["ae_papers"]
        ay["total"] += s["total_papers"]
        ay["avail"] += s["available"]
        ay["func"] += s["functional"]
        ay["repro"] += s["reproduced"]

    area_summaries = {}
    for area in sorted(area_year):
        years = sorted(area_year[area])
        area_summaries[area] = {
            "years": years,
            "participation_pct": [
                round(area_year[area][y]["ae"] / area_year[area][y]["total"] * 100, 1)
                for y in years
            ],
            "available_pct": [
                round(area_year[area][y]["avail"] / area_year[area][y]["total"] * 100, 1)
                for y in years
            ],
            "functional_pct": [
                round(area_year[area][y]["func"] / area_year[area][y]["total"] * 100, 1)
                for y in years
            ],
            "reproduced_pct": [
                round(area_year[area][y]["repro"] / area_year[area][y]["total"] * 100, 1)
                for y in years
            ],
        }

    output = {
        "by_conference_year": stats,
        "by_area": area_summaries,
    }

    # Write outputs
    os.makedirs(os.path.join(output_dir, "_data"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "assets/data"), exist_ok=True)

    yml_path = os.path.join(output_dir, "_data/participation_stats.yml")
    with open(yml_path, "w") as f:
        yaml.dump(output, f, default_flow_style=False, sort_keys=False)

    json_path = os.path.join(output_dir, "assets/data/participation_stats.json")
    with open(json_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✅ Participation stats: {len(stats)} conference/year entries")
    print(f"   → {yml_path}")
    print(f"   → {json_path}")

    return output


def main():
    parser = argparse.ArgumentParser(
        description="Generate AE participation statistics from DBLP XML paper counts"
    )
    parser.add_argument(
        "--dblp_file",
        type=str,
        default="data/dblp/dblp.xml.gz",
        help="Path to dblp.xml.gz",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        required=True,
        help="Output directory (same as generate_statistics output_dir)",
    )
    args = parser.parse_args()
    generate_participation_stats(args.dblp_file, args.output_dir)


if __name__ == "__main__":
    main()
