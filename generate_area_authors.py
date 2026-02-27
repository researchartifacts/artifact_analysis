#!/usr/bin/env python3
"""
Generate per-area (systems/security) author data files for the Jekyll site.
Reads _data/authors.yml and _data/summary.yml, outputs:
  - _data/systems_authors.yml
  - _data/security_authors.yml

Usage:
  python generate_area_authors.py --data_dir ../researchartifacts.github.io
"""

import yaml
import json
import os
import argparse
from collections import defaultdict

DATA_DIR = None  # Set via CLI


def load_yaml(filename):
    with open(os.path.join(DATA_DIR, filename), 'r') as f:
        return yaml.safe_load(f)


def save_yaml(filename, data):
    with open(os.path.join(DATA_DIR, filename), 'w') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def generate_area_authors():
    summary = load_yaml('summary.yml')
    authors = load_yaml('authors.yml')

    systems_confs = set(summary.get('systems_conferences', []))
    security_confs = set(summary.get('security_conferences', []))

    # Determine year range from artifacts_by_year (global fallback)
    by_year = load_yaml('artifacts_by_year.yml')
    all_years = sorted([entry['year'] for entry in by_year], reverse=True)
    min_year = min(all_years)
    max_year = max(all_years)

    # Compute per-conference AE year ranges from actual artifact data
    artifacts_by_conf = load_yaml('artifacts_by_conference.yml')
    conf_ae_years = {}   # conf_name -> set of years with AE data
    for conf_data in artifacts_by_conf:
        name = conf_data['name']
        ae_years = set()
        for yr_data in conf_data.get('years', []):
            ae_years.add(yr_data['year'])
        if ae_years:
            conf_ae_years[name] = ae_years

    def process_authors_for_area(authors_list, area_confs, area_name):
        """Extract per-area author stats."""
        # Compute year range from actual AE data for THIS area's conferences only
        area_ae_years = set()
        for conf in area_confs:
            area_ae_years |= conf_ae_years.get(conf, set())
        area_min_year = min(area_ae_years) if area_ae_years else min_year
        area_max_year = max(area_ae_years) if area_ae_years else max_year
        area_last_5_start = area_max_year - 4

        area_authors = []
        for author in authors_list:
            papers = author.get('papers', [])
            # Filter papers to this area's conferences
            area_papers = [p for p in papers if p.get('conference', '') in area_confs]
            if not area_papers:
                continue

            total = len(area_papers)
            # Count per year
            year_counts = defaultdict(int)
            for p in area_papers:
                yr = p.get('year')
                if yr:
                    year_counts[yr] += 1

            last_5 = sum(year_counts.get(y, 0) for y in range(area_last_5_start, area_max_year + 1))

            # Build per-year list (only area's AE year range)
            years_data = {}
            for y in range(area_max_year, area_min_year - 1, -1):
                years_data[y] = year_counts.get(y, 0)

            # Count badges in this area
            badges_available = 0
            badges_functional = 0
            badges_reproducible = 0
            for p in area_papers:
                for b in p.get('badges', []):
                    bl = b.lower() if isinstance(b, str) else ''
                    if 'available' in bl:
                        badges_available += 1
                    if 'functional' in bl:
                        badges_functional += 1
                    if 'reproduc' in bl or 'reproduced' in bl:
                        badges_reproducible += 1

            # --- Compute total papers at area conferences (AE years only) ---
            # Only count papers published in years where AE existed for that conference.
            area_total_papers = 0
            per_conf_year_totals = author.get('total_papers_by_conf_year', {})
            per_conf_totals = author.get('total_papers_by_conf', {})
            for conf in area_confs:
                ae_years = conf_ae_years.get(conf, set())
                conf_year_data = per_conf_year_totals.get(conf, {})
                if conf_year_data and ae_years:
                    # Sum only papers from AE years
                    for yr, cnt in conf_year_data.items():
                        yr_int = int(yr) if not isinstance(yr, int) else yr
                        if yr_int in ae_years:
                            area_total_papers += cnt
                elif ae_years:
                    # Fallback: per-conf total (no year breakdown available)
                    area_total_papers += per_conf_totals.get(conf, 0)
                else:
                    # No AE years known, use full count
                    area_total_papers += per_conf_totals.get(conf, 0)

            # Rates — cap artifact_rate at 100% (can exceed if DBLP title
            # matching misses some venue papers but artifact matching finds them)
            artifact_rate = round(min(total / area_total_papers * 100, 100.0), 1) if area_total_papers > 0 else 0.0
            repro_rate = round(badges_reproducible / total * 100, 1) if total > 0 else 0.0
            functional_rate = round(badges_functional / total * 100, 1) if total > 0 else 0.0

            # Weighted artifact score (same weights as combined rankings):
            #   Reproducible = 3 pts, Functional-only = 2 pts, Available-only = 1 pt
            repro = badges_reproducible
            func_only = max(0, badges_functional - badges_reproducible)
            remainder = max(0, total - badges_functional)
            artifact_score = repro * 3 + func_only * 2 + remainder * 1

            entry = {
                'name': author['name'],
                'artifact_score': artifact_score,
                'total': total,
                'total_papers': area_total_papers,
                'artifact_rate': artifact_rate,
                'repro_rate': repro_rate,
                'functional_rate': functional_rate,
                'last_5_years': last_5,
                'badges_available': badges_available,
                'badges_functional': badges_functional,
                'badges_reproducible': badges_reproducible,
                'conferences': sorted(set(p.get('conference', '') for p in area_papers)),
                'years': years_data,
            }
            area_authors.append(entry)

        # Sort by artifact_score descending, then by total descending, then by name
        area_authors.sort(key=lambda x: (-x['artifact_score'], -x['total'], x['name']))

        # Assign ranks (with ties on artifact_score)
        rank = 1
        for i, a in enumerate(area_authors):
            if i > 0 and a['artifact_score'] < area_authors[i - 1]['artifact_score']:
                rank = i + 1
            a['rank'] = rank

        return area_authors

    systems_authors = process_authors_for_area(authors, systems_confs, 'systems')
    security_authors = process_authors_for_area(authors, security_confs, 'security')

    # Save YAML for Jekyll (kept for backwards compat, but pages now load JSON)
    save_yaml('systems_authors.yml', systems_authors)
    save_yaml('security_authors.yml', security_authors)

    # Save JSON for dynamic client-side loading (much faster page load)
    assets_data = os.path.join(DATA_DIR, '..', 'assets', 'data')
    os.makedirs(assets_data, exist_ok=True)
    with open(os.path.join(assets_data, 'systems_authors.json'), 'w') as f:
        json.dump(systems_authors, f, ensure_ascii=False)
    with open(os.path.join(assets_data, 'security_authors.json'), 'w') as f:
        json.dump(security_authors, f, ensure_ascii=False)

    # --- Generate per-conference author JSON files ---
    all_confs = systems_confs | security_confs
    for conf in sorted(all_confs):
        conf_authors = process_authors_for_area(authors, {conf}, conf)
        fname = f"{conf.lower()}_conf_authors.json"
        with open(os.path.join(assets_data, fname), 'w') as f:
            json.dump(conf_authors, f, ensure_ascii=False)
        print(f"  {conf}: {len(conf_authors)} authors -> assets/data/{fname}")

    # Update author_summary with correct counts
    author_summary = load_yaml('author_summary.yml')
    author_summary['systems_authors'] = len(systems_authors)
    author_summary['security_authors'] = len(security_authors)

    # Count cross-domain authors
    sys_names = set(a['name'] for a in systems_authors)
    sec_names = set(a['name'] for a in security_authors)
    author_summary['cross_domain_authors'] = len(sys_names & sec_names)
    save_yaml('author_summary.yml', author_summary)

    print(f"Generated {len(systems_authors)} systems authors -> _data/systems_authors.yml")
    print(f"Generated {len(security_authors)} security authors -> _data/security_authors.yml")
    print(f"Cross-domain authors: {len(sys_names & sec_names)}")
    print(f"Global year range from artifacts_by_year: {min_year}-{max_year}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate per-area author data files.')
    parser.add_argument('--data_dir', type=str, default='../researchartifacts.github.io',
                        help='Path to the website repo root (containing _data/)')
    args = parser.parse_args()
    DATA_DIR = os.path.join(args.data_dir, '_data')
    generate_area_authors()
