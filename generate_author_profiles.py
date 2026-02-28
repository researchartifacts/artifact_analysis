#!/usr/bin/env python3
"""
Generate author_profiles.json by merging data from:
  - assets/data/authors.json       (per-paper artifact details)
  - assets/data/ae_members.json    (AE committee service details)
  - assets/data/combined_rankings.json (weighted scores & ranks)

Output:
  assets/data/author_profiles.json — one entry per author with full profile data,
  suitable for client-side rendering of individual author profile pages.

Usage:
  python generate_author_profiles.py --data_dir ../researchartifacts.github.io
"""

import json
import os
import argparse


def generate_profiles(data_dir: str) -> None:
    authors_path = os.path.join(data_dir, 'assets/data/authors.json')
    ae_path = os.path.join(data_dir, 'assets/data/ae_members.json')
    cr_path = os.path.join(data_dir, 'assets/data/combined_rankings.json')
    out_path = os.path.join(data_dir, 'assets/data/author_profiles.json')

    # Load data sources
    with open(authors_path) as f:
        authors = json.load(f)
    with open(ae_path) as f:
        ae_members = json.load(f)
    with open(cr_path) as f:
        combined = json.load(f)

    # Index by cleaned name for lookups
    def clean(s: str) -> str:
        """Normalize whitespace (tabs, double spaces, etc.) to single space."""
        return ' '.join(s.split())

    ae_by_name = {clean(m['name']): m for m in ae_members}
    cr_by_name = {clean(c['name']): c for c in combined}

    profiles: dict[str, dict] = {}

    # Build profiles from artifact authors
    for a in authors:
        name = clean(a['name'])
        cr = cr_by_name.get(name)
        ae = ae_by_name.get(name)

        profile: dict = {
            'name': name,
            'affiliation': clean(a.get('affiliation') or
                            (cr.get('affiliation', '') if cr else '') or
                            (ae.get('affiliation', '') if ae else '')),
            'papers': a.get('papers', []),
            'conferences': a.get('conferences', []),
            'years': a.get('years', []),
            'artifact_count': a.get('artifact_count', 0),
            'total_papers': a.get('total_papers', 0),
            'artifact_rate': a.get('artifact_rate', 0),
            'badges_available': a.get('badges_available', 0),
            'badges_functional': a.get('badges_functional', 0),
            'badges_reproducible': a.get('badges_reproducible', 0),
            'category': a.get('category', 'unknown'),
        }

        if cr:
            profile['combined_score'] = cr.get('combined_score', 0)
            profile['artifact_score'] = cr.get('artifact_score', 0)
            profile['ae_score'] = cr.get('ae_score', 0)
            profile['rank'] = cr.get('rank', 0)

        if ae:
            profile['ae_memberships'] = ae.get('total_memberships', 0)
            profile['chair_count'] = ae.get('chair_count', 0)
            profile['ae_conferences'] = ae.get('conferences', [])
            profile['ae_years'] = ae.get('years', {})

        profiles[name] = profile

    # Add AE-only members not in authors
    for m in ae_members:
        cname = clean(m['name'])
        if cname in profiles:
            continue
        cr = cr_by_name.get(cname)
        profile = {
            'name': cname,
            'affiliation': clean(m.get('affiliation', '') or
                            (cr.get('affiliation', '') if cr else '')),
            'papers': [],
            'conferences': m.get('conferences', []),
            'years': sorted(int(y) for y in m.get('years', {}).keys()),
            'artifact_count': 0,
            'total_papers': 0,
            'artifact_rate': 0,
            'badges_available': 0,
            'badges_functional': 0,
            'badges_reproducible': 0,
            'category': m.get('area', 'unknown'),
            'ae_memberships': m.get('total_memberships', 0),
            'chair_count': m.get('chair_count', 0),
            'ae_conferences': m.get('conferences', []),
            'ae_years': m.get('years', {}),
        }
        if cr:
            profile['combined_score'] = cr.get('combined_score', 0)
            profile['artifact_score'] = cr.get('artifact_score', 0)
            profile['ae_score'] = cr.get('ae_score', 0)
            profile['rank'] = cr.get('rank', 0)
        profiles[m['name']] = profile

    # Sort by combined_score desc, then artifact_count desc, then name asc
    profile_list = sorted(
        profiles.values(),
        key=lambda x: (-x.get('combined_score', 0),
                       -x.get('artifact_count', 0),
                       x['name'])
    )

    # Write compact JSON
    with open(out_path, 'w') as f:
        json.dump(profile_list, f, ensure_ascii=False, separators=(',', ':'))

    print(f"Wrote {out_path} ({len(profile_list)} profiles, "
          f"{os.path.getsize(out_path) / 1024:.0f}KB)")
    print(f"  Authors with papers: "
          f"{sum(1 for p in profile_list if p['papers'])}")
    print(f"  Authors with AE service: "
          f"{sum(1 for p in profile_list if p.get('ae_memberships', 0) > 0)}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate author profile JSON for the website')
    parser.add_argument(
        '--data_dir', type=str, required=True,
        help='Path to the researchartifacts.github.io directory')
    args = parser.parse_args()
    generate_profiles(args.data_dir)


if __name__ == '__main__':
    main()
