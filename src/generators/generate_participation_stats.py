#!/usr/bin/env python3
"""
Generate AE participation statistics by querying DBLP for total paper counts.

For each conference/year in the pipeline's artifacts data, this script:
1. Queries DBLP to get the total number of papers for that venue/year.
2. Computes AE participation rate (ae_papers / total_papers).
3. Computes badge rates as % of all papers (not just AE papers).

Writes:
  _data/participation_stats.yml     — per-conference/year participation data
  assets/data/participation_stats.json — same data in JSON

Usage:
  python -m src.generators.generate_participation_stats \
      --conf_regex '.*20[12][0-9]' --output_dir ../researchartifacts.github.io
"""

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
import yaml
from collections import defaultdict
from urllib.parse import quote

from ..scrapers.sys_sec_scrape import _read_cache, _write_cache

# ── DBLP conference key mapping ──────────────────────────────────────
# Two strategies:
#   "toc" — use DBLP TOC endpoint (precise proceedings match)
#   "venue" — use DBLP venue search (broader, for conferences with
#             non-standard keys)

DBLP_MAP = {
    "USENIXSEC": ("toc", "uss", "conf"),
    "OSDI":      ("toc", "osdi", "conf"),
    "ACSAC":     ("toc", "acsac", "conf"),
    "SOSP":      ("toc", "sosp", "conf"),
    "NDSS":      ("toc", "ndss", "conf"),
    "ATC":       ("toc", "usenix", "conf"),
    "WOOT":      ("toc", "woot", "conf"),
    "PETS":      ("toc", "popets", "journals"),
    "CHES":      ("toc", "tches", "journals"),
    "EUROSYS":   ("venue", "EuroSys", None),
    "FAST":      ("venue", "FAST", None),
    "SC":        ("venue", "SC", None),
    # SYSTEX: tiny workshop, not reliably indexed in DBLP
}

AREA_MAP = {
    "USENIXSEC": "security", "NDSS": "security", "ACSAC": "security",
    "PETS": "security", "CHES": "security", "WOOT": "security",
    "OSDI": "systems", "SOSP": "systems", "ATC": "systems",
    "EUROSYS": "systems", "FAST": "systems", "SC": "systems",
    "SYSTEX": "security",
}

CACHE_NAMESPACE = "dblp_paper_counts"
CACHE_TTL = 86400 * 30  # 30 days


def _normalize_title(t):
    """Lowercase, strip punctuation/whitespace for fuzzy matching."""
    return re.sub(r"[^\w\s]", "", t.lower()).strip()


def _dblp_request(url):
    """Make a DBLP API request with retries and caching."""
    cached = _read_cache(url, ttl=CACHE_TTL, namespace=CACHE_NAMESPACE)
    if cached is not None:
        return cached

    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "ResearchArtifacts/1.0"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
            _write_cache(url, data, namespace=CACHE_NAMESPACE)
            return data
        except (urllib.error.HTTPError, urllib.error.URLError, ConnectionError) as e:
            if attempt < 2:
                wait = 3 * (attempt + 1)
                print(f"  ⚠ DBLP error ({e}), retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"  ✗ DBLP failed after 3 attempts: {e}")
                return None


def _fetch_dblp_paper_count(conf, year):
    """Fetch total paper count for a conference/year from DBLP."""
    if conf not in DBLP_MAP:
        return None

    strategy, key, key_type = DBLP_MAP[conf]

    if strategy == "toc":
        if key_type == "journals":
            path = f"db/journals/{key}/{key}{year}"
        else:
            path = f"db/conf/{key}/{key}{year}"
        q = f"toc:{path}.bht:"
    else:
        q = f"venue:{key}: year:{year}: type:Conference_and_Workshop_Papers:"

    url = f"https://dblp.org/search/publ/api?q={quote(q)}&format=json&h=1000"
    data = _dblp_request(url)
    if not data:
        return None

    hits = data.get("result", {}).get("hits", {})
    total = int(hits.get("@total", 0))
    return total


def _extract_conf_year(conf_year_str):
    """Extract conference name and year from 'confYYYY' string."""
    m = re.match(r"^([a-zA-Z]+)(\d{4})$", conf_year_str)
    if m:
        return m.group(1).upper(), int(m.group(2))
    return conf_year_str.upper(), None


def generate_participation_stats(conf_regex=".*20[12][0-9]", output_dir=None):
    """Generate AE participation and badge-rate statistics."""

    if not output_dir:
        print("Error: --output_dir is required")
        return

    # Load artifacts data produced by generate_statistics
    artifacts_path = os.path.join(output_dir, "assets/data/artifacts.json")
    if not os.path.exists(artifacts_path):
        print(f"Error: {artifacts_path} not found — run generate_statistics first")
        return

    with open(artifacts_path) as f:
        artifacts = json.load(f)

    # Load artifacts_by_conference for per-conference badge counts
    abc_path = os.path.join(output_dir, "_data/artifacts_by_conference.yml")
    with open(abc_path) as f:
        by_conference = yaml.safe_load(f)

    # Build per-conference/year AE counts and badge counts from pipeline data
    ae_data = {}  # (conf, year) -> {total, available, functional, reproduced}
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

    # Query DBLP for total paper counts
    print(f"Fetching DBLP paper counts for {len(ae_data)} conference/year entries...")
    stats = []
    for (conf, year), info in sorted(ae_data.items()):
        if not re.search(conf_regex, f"{conf.lower()}{year}"):
            continue
        if conf not in DBLP_MAP:
            print(f"  ⚠ Skipping {conf} {year} (no DBLP mapping)")
            continue

        time.sleep(0.5)  # rate limiting
        total_papers = _fetch_dblp_paper_count(conf, year)
        if total_papers is None or total_papers == 0:
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
        description="Generate AE participation statistics from DBLP paper counts"
    )
    parser.add_argument(
        "--conf_regex",
        type=str,
        default=".*20[12][0-9]",
        help="Regular expression for conference names/years",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        required=True,
        help="Output directory (same as generate_statistics output_dir)",
    )
    args = parser.parse_args()
    generate_participation_stats(args.conf_regex, args.output_dir)


if __name__ == "__main__":
    main()
