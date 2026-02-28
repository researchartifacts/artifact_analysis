#!/usr/bin/env python3
"""
Generate combined rankings that merge artifact authorship with AE committee
service.  Reads the per-area author JSON and AE member JSON produced by
earlier pipeline stages and writes combined JSON files for the Jekyll site.

Outputs:
  assets/data/combined_rankings.json
  assets/data/systems_combined_rankings.json
  assets/data/security_combined_rankings.json
  _data/combined_summary.yml

Usage:
  python generate_combined_rankings.py --data_dir ../researchartifacts.github.io
"""

import json
import os
import re
import argparse
import unicodedata
import yaml
from collections import defaultdict


# ── Name normalisation ────────────────────────────────────────────────────────

_DBLP_SUFFIX = re.compile(r'\s+\d{4}$')        # e.g. "Haibo Chen 0001"
_INITIALS    = re.compile(r'\b[A-Z]\.\s*')      # e.g. "J. Doe"
_MULTI_SPACE = re.compile(r'\s+')


def _normalize_name(name: str) -> str:
    """Normalise a name for cross-dataset matching.

    Steps: NFKD unicode → lower-case → strip DBLP disambiguation suffix →
    strip single-letter initials → collapse whitespace → strip.
    """
    name = unicodedata.normalize('NFKD', name)
    name = name.lower()
    name = _DBLP_SUFFIX.sub('', name)
    name = _INITIALS.sub('', name)
    name = _MULTI_SPACE.sub(' ', name).strip()
    # Strip leading underscores (artefact of some scraping)
    name = name.lstrip('_').strip()
    return name


# ── Merge logic ───────────────────────────────────────────────────────────────

def _merge_rankings(authors: list, ae_members: list) -> list:
    """Merge author and AE-member lists into a combined ranking.

    Matching is done on normalised names.  Every person appearing in *either*
    list gets an entry.  Fields from both sources are combined.

    When multiple DBLP authors share the same normalised name as an AE member
    (common for East-Asian names with DBLP disambiguation suffixes), conference
    overlap is used to pick the best match.  Only the winning author receives
    the AE member's committee data; others keep their paper data alone.  If no
    clear winner can be determined, the AE member appears as a standalone entry.

    Returns a list of dicts sorted by combined_score descending.
    """

    # Index AE members by normalised name
    member_by_norm: dict[str, dict] = {}
    for m in ae_members:
        norm = _normalize_name(m['name'])
        # If multiple AE entries map to the same norm (unlikely but possible),
        # keep the one with higher memberships.
        if norm in member_by_norm:
            if m.get('total_memberships', 0) > member_by_norm[norm].get('total_memberships', 0):
                member_by_norm[norm] = m
        else:
            member_by_norm[norm] = m

    # ── Disambiguation: when several DBLP authors share the same normalised
    #    name as an AE member, pick the best match via conference overlap. ────
    author_groups: dict[str, list[dict]] = defaultdict(list)
    for a in authors:
        author_groups[_normalize_name(a['name'])].append(a)

    # Maps normalised name → the single DBLP author name that should receive
    # AE data, or None if no safe match could be determined.
    _ae_winner: dict[str, str | None] = {}
    _ambiguous_norms: set[str] = set()

    for norm, group in author_groups.items():
        if norm not in member_by_norm:
            continue  # no AE member to match

        if len(group) == 1:
            _ae_winner[norm] = group[0]['name']  # unambiguous
            continue

        # Multiple DBLP authors share this normalised name — disambiguate
        ae_confs = set(member_by_norm[norm].get('conferences', []))
        scored = []
        for a in group:
            overlap = len(set(a.get('conferences', [])) & ae_confs)
            scored.append((overlap, a['name']))
        scored.sort(key=lambda x: -x[0])

        if scored[0][0] > 0 and (len(scored) < 2 or scored[0][0] > scored[1][0]):
            # Clear winner — unique best conference overlap
            _ae_winner[norm] = scored[0][1]
            print(f"  Disambiguated '{norm}': {scored[0][1]} "
                  f"(conf overlap {scored[0][0]}) wins over "
                  f"{[s[1] for s in scored[1:]]}")
        else:
            # Ambiguous — don't link anyone; AE member appears standalone
            _ae_winner[norm] = None
            _ambiguous_norms.add(norm)
            print(f"  AMBIGUOUS '{norm}': {[s[1] for s in scored]} "
                  f"(overlaps: {[s[0] for s in scored]}) — AE member unlinked")

    if _ambiguous_norms:
        print(f"  ⚠ {len(_ambiguous_norms)} AE members could not be "
              f"unambiguously linked to a DBLP author")

    linked_ae_norms: set[str] = set()
    combined: list[dict] = []

    # 1. Walk authors — attach AE data only to the designated winner
    for a in authors:
        norm = _normalize_name(a['name'])

        is_winner = (norm in _ae_winner and _ae_winner[norm] == a['name'])
        m = member_by_norm.get(norm) if is_winner else None

        if m is not None:
            linked_ae_norms.add(norm)

        artifacts = a.get('total', a.get('artifact_count', 0)) or 0
        ae_memberships = m['total_memberships'] if m else 0
        chair_count = m['chair_count'] if m else 0

        # Merge year activity – author years can be a dict {year: count}
        # or a list [2020, 2022, …]
        raw_years = a.get('years', {})
        if isinstance(raw_years, list):
            years = {int(y): 1 for y in raw_years}
        else:
            years = {int(k): v for k, v in raw_years.items()}
        if m:
            for yr, cnt in m.get('years', {}).items():
                yr_key = int(yr) if not isinstance(yr, int) else yr
                # Keep max of both (they track different things, but for the
                # combined view we just want to know the person was active).
                years[yr_key] = max(years.get(yr_key, 0), cnt)

        # Merge conferences
        a_confs = set(a.get('conferences', []))
        m_confs = set(m.get('conferences', [])) if m else set()

        entry = _build_entry(
            name=a['name'],
            affiliation=m.get('affiliation', '') if m else '',
            artifacts=artifacts,
            total_papers=a.get('total_papers', 0) or 0,
            artifact_rate=a.get('artifact_rate', 0) or 0,
            ae_memberships=ae_memberships,
            chair_count=chair_count,
            conferences=sorted(a_confs | m_confs),
            years=years,
            badges_available=a.get('badges_available', 0) or 0,
            badges_functional=a.get('badges_functional', 0) or 0,
            badges_reproducible=a.get('badges_reproducible', 0) or 0,
        )
        combined.append(entry)

    # 2. Walk AE members not already linked to a winning author
    for norm, m in member_by_norm.items():
        if norm in linked_ae_norms:
            continue

        years = {}
        for yr, cnt in m.get('years', {}).items():
            yr_key = int(yr) if not isinstance(yr, int) else yr
            years[yr_key] = cnt

        entry = _build_entry(
            name=m['name'],
            affiliation=m.get('affiliation', ''),
            artifacts=0,
            total_papers=0,
            artifact_rate=0,
            ae_memberships=m.get('total_memberships', 0),
            chair_count=m.get('chair_count', 0),
            conferences=sorted(m.get('conferences', [])),
            years=years,
            badges_available=0,
            badges_functional=0,
            badges_reproducible=0,
        )
        combined.append(entry)

    # Sort by combined_score desc, then artifacts desc, then name asc
    combined.sort(key=lambda x: (-x['combined_score'], -x['artifacts'], x['name']))

    # Assign ranks (with ties on combined_score)
    rank = 1
    for i, c in enumerate(combined):
        if i > 0 and c['combined_score'] < combined[i - 1]['combined_score']:
            rank = i + 1
        c['rank'] = rank

    return combined


# ── Scoring weights ───────────────────────────────────────────────────────────
# Artifact badges:  Available-only = 1,  Functional-only = 2,  Reproducible = 3
# AE service:       Each membership = 3,  Each chair role = +2  (on top of membership)
W_AVAILABLE   = 1
W_FUNCTIONAL  = 2
W_REPRODUCIBLE = 3
W_AE_MEMBERSHIP = 3
W_AE_CHAIR      = 2   # bonus on top of membership


def _build_entry(*, name, affiliation, artifacts, total_papers, artifact_rate,
                 ae_memberships, chair_count, conferences, years,
                 badges_available, badges_functional, badges_reproducible) -> dict:
    """Build a single combined-ranking entry dict with weighted scoring.

    Scoring:
      artifact_score = reproducible*3 + (functional-reproducible)*2 + remainder*1
      ae_score       = memberships*3  + chairs*2
      combined_score = artifact_score + ae_score
    """
    # Compute weighted artifact score
    repro    = badges_reproducible
    func_only = max(0, badges_functional - badges_reproducible)
    remainder = max(0, artifacts - badges_functional)
    artifact_score = (repro * W_REPRODUCIBLE
                      + func_only * W_FUNCTIONAL
                      + remainder * W_AVAILABLE)

    # Compute weighted AE score
    ae_score = ae_memberships * W_AE_MEMBERSHIP + chair_count * W_AE_CHAIR

    combined_score = artifact_score + ae_score

    yr_keys = [int(y) for y in years.keys()] if years else []
    return {
        'name': name,
        'affiliation': affiliation,
        'artifacts': artifacts,
        'artifact_score': artifact_score,
        'total_papers': total_papers,
        'artifact_rate': artifact_rate,
        'ae_memberships': ae_memberships,
        'chair_count': chair_count,
        'ae_score': ae_score,
        'combined_score': combined_score,
        'badges_available': badges_available,
        'badges_functional': badges_functional,
        'badges_reproducible': badges_reproducible,
        'conferences': conferences,
        'years': years,
        'first_year': min(yr_keys) if yr_keys else None,
        'last_year': max(yr_keys) if yr_keys else None,
    }


# ── Main entry ────────────────────────────────────────────────────────────────

def generate_combined_rankings(data_dir: str):
    """Read author + AE data, write combined ranking files."""

    assets_data = os.path.join(data_dir, 'assets', 'data')
    yaml_dir = os.path.join(data_dir, '_data')

    # Load author data
    def _load_json(name):
        path = os.path.join(assets_data, name)
        if not os.path.exists(path):
            print(f"  Warning: {name} not found, skipping")
            return []
        with open(path) as f:
            return json.load(f)

    all_authors   = _load_json('authors.json')
    sys_authors   = _load_json('systems_authors.json')
    sec_authors   = _load_json('security_authors.json')
    all_members   = _load_json('ae_members.json')
    sys_members   = _load_json('systems_ae_members.json')
    sec_members   = _load_json('security_ae_members.json')

    # Generate combined rankings
    combined_all = _merge_rankings(all_authors, all_members)
    combined_sys = _merge_rankings(sys_authors, sys_members)
    combined_sec = _merge_rankings(sec_authors, sec_members)

    # Filter: only include people with combined_score >= 3
    # With weighted scoring (Available=1, Functional=2, Reproducible=3,
    # AE membership=3, AE chair=+2), a score of 3 means at least one
    # reproducible artifact, or one AE membership, or meaningful contribution.
    combined_all = [c for c in combined_all if c['combined_score'] >= 3]
    combined_sys = [c for c in combined_sys if c['combined_score'] >= 3]
    combined_sec = [c for c in combined_sec if c['combined_score'] >= 3]

    # Re-rank after filtering
    for lst in (combined_all, combined_sys, combined_sec):
        rank = 1
        for i, c in enumerate(lst):
            if i > 0 and c['combined_score'] < lst[i - 1]['combined_score']:
                rank = i + 1
            c['rank'] = rank

    # Write JSON
    os.makedirs(assets_data, exist_ok=True)
    for fname, data in [
        ('combined_rankings.json', combined_all),
        ('systems_combined_rankings.json', combined_sys),
        ('security_combined_rankings.json', combined_sec),
    ]:
        path = os.path.join(assets_data, fname)
        with open(path, 'w') as f:
            json.dump(data, f, ensure_ascii=False)
        print(f"  Wrote {path} ({len(data)} entries)")

    # Summary YAML
    # Count people who have both artifacts AND AE service
    both_all = sum(1 for c in combined_all if c['artifacts'] > 0 and c['ae_memberships'] > 0)
    both_sys = sum(1 for c in combined_sys if c['artifacts'] > 0 and c['ae_memberships'] > 0)
    both_sec = sum(1 for c in combined_sec if c['artifacts'] > 0 and c['ae_memberships'] > 0)

    summary = {
        'combined_total': len(combined_all),
        'combined_systems': len(combined_sys),
        'combined_security': len(combined_sec),
        'both_artifacts_and_ae': both_all,
        'both_artifacts_and_ae_systems': both_sys,
        'both_artifacts_and_ae_security': both_sec,
        'top_combined_score': combined_all[0]['combined_score'] if combined_all else 0,
    }
    yml_path = os.path.join(yaml_dir, 'combined_summary.yml')
    with open(yml_path, 'w') as f:
        yaml.dump(summary, f, default_flow_style=False, sort_keys=False)
    print(f"  Wrote {yml_path}")

    print(f"  Combined rankings: {len(combined_all)} total, "
          f"{len(combined_sys)} systems, {len(combined_sec)} security")
    print(f"  People with both artifacts and AE service: {both_all}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate combined artifact-author + AE-member rankings')
    parser.add_argument('--data_dir', type=str,
                        default='../researchartifacts.github.io',
                        help='Path to the website repo root')
    args = parser.parse_args()
    generate_combined_rankings(args.data_dir)


if __name__ == '__main__':
    main()
