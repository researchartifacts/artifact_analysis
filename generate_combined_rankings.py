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


# Mapping: compiled regex  →  canonical name
# Order matters: more specific patterns must come before broader ones.
_AFFILIATION_RULES: list[tuple[re.Pattern, str]] = [
    # ── Short-form abbreviations → full canonical names ─────────────────────
    # MIT
    (re.compile(r'^MIT\b|\bMIT\b.*\b(Cambridge|CSAIL|Lincoln)\b|\bMassachusetts\s+Institute\s+of\s+Technology\b|\bMassachusetts\s+Inst\.?\s+of\s+Technology\b', re.I),
     'Massachusetts Institute of Technology'),

    # EPFL
    (re.compile(r'^EPFL\b|\bEPFL\b|\bSwiss\s+Federal\s+Institute\s+of\s+Technology\s+in\s+Lausanne\b|\bEcole\s+Polytechnique\s+Federale\s+de\s+Lausanne\b|\bÉcole\s+Polytechnique\s+Fédérale\s+de\s+Lausanne\b', re.I),
     'EPFL'),

    # ETH Zurich  (careful not to match "Netherlands", "Eindhoven" etc.)
    (re.compile(r'^ETH\b|^ETH\s+Z|\bETH\s+Zurich\b|\bETH\s+Zrich\b|\bETH\s+Zürich\b|\bETHZ\b|^Department\s+of\s+Computer\s+Science,\s+ETH', re.I),
     'ETH Zurich'),

    # ── Max Planck institutes ──────────────────────────────────────────────
    (re.compile(r'Max\s+Planck.*Software\s+Systems|\bMPI[- ]?SWS\b', re.I),
     'Max Planck Institute for Software Systems'),
    (re.compile(r'Max\s+Planck.*Security\s+and\s+Privacy|\bMPI[- ]?SP\b', re.I),
     'Max Planck Institute for Security and Privacy'),
    (re.compile(r'Max\s+Planck.*Informatics\b', re.I),
     'Max Planck Institute for Informatics'),

    # ── CISPA ──────────────────────────────────────────────────────────────
    (re.compile(r'^CISPA\b|\bCISPA\s+Helmholtz\b', re.I),
     'CISPA Helmholtz Center for Information Security'),

    # ── UC campuses ────────────────────────────────────────────────────────
    (re.compile(r'UC\s+Berkeley|University\s+of\s+California,?\s+Berkeley|University\s+of\s+California\s+at\s+Berkeley', re.I),
     'University of California, Berkeley'),
    (re.compile(r'UC\s+San\s+Diego|UCSD|University\s+of\s+California,?\s+San\s+Diego', re.I),
     'University of California, San Diego'),
    (re.compile(r'UC\s+Santa\s+Barbara|UCSB|University\s+of\s+California,?\s+Santa\s+Barbara', re.I),
     'University of California, Santa Barbara'),
    (re.compile(r'UC\s+Santa\s+Cruz|University\s+of\s+California,?\s+Santa\s+Cruz', re.I),
     'University of California, Santa Cruz'),
    (re.compile(r'UC\s+Davis|University\s+of\s+California,?\s+Davis', re.I),
     'University of California, Davis'),
    (re.compile(r'UC\s+Irvine|University\s+of\s+California,?\s+Irvine|University\s+of\s+California\s+Irvine', re.I),
     'University of California, Irvine'),
    (re.compile(r'UC\s+Riverside|University\s+of\s+California,?\s+Riverside', re.I),
     'University of California, Riverside'),
    (re.compile(r'UC\s+Los\s+Angeles|UCLA|University\s+of\s+California,?\s+Los\s+Angeles', re.I),
     'University of California, Los Angeles'),
    (re.compile(r'UC\s+Merced|University\s+of\s+California,?\s+Merced', re.I),
     'University of California, Merced'),

    # ── Lawrence Berkeley National Laboratory ─────────────────────────────
    (re.compile(r'Lawrence\s+Berkeley\s+National\s+Laboratory|\bLBNL\b', re.I),
     'Lawrence Berkeley National Laboratory'),

    # ── UIUC / Illinois ───────────────────────────────────────────────────
    (re.compile(r'\bUIUC\b|Univ\.?\s+of\s+Illinois\s+at\s+Urbana|University\s+of\s+Illinois\s+at\s+Urbana|University\s+of\s+Illinois\s+Urbana|University\s+of\s+Illinois,\s+Urbana', re.I),
     'University of Illinois Urbana-Champaign'),

    # ── UCL London (not UCLouvain) ────────────────────────────────────────
    (re.compile(r'^UCL$|^UCL,|\bUniversity\s+College\s+London\b', re.I),
     'University College London'),

    # ── VU Amsterdam ──────────────────────────────────────────────────────
    (re.compile(r'\bVU\s+Amsterdam\b|\bVrije\s+Universiteit\b', re.I),
     'Vrije Universiteit Amsterdam'),

    # ── Ruhr University Bochum ────────────────────────────────────────────
    (re.compile(r'Ruhr[- ]Universit(?:y|ät)\s+(?:of\s+)?Bochum|Ruhr\s+University\s+Bochum', re.I),
     'Ruhr University Bochum'),

    # ── University of Wisconsin-Madison ───────────────────────────────────
    (re.compile(r'University\s+of\s+Wisconsin[\s–—-]+Madison|\bUW\s*[-–—]?\s*Madison\b|\bUW\s*[-–—]?\s*Mad\b', re.I),
     'University of Wisconsin-Madison'),

    # ── University of Michigan ───────────────────────────────────────────
    (re.compile(r'\bU\s+Michigan\b|\bUMich\b|\bUMichigan\b|University\s+of\s+Michigan', re.I),
     'University of Michigan'),

    # ── TU Delft / Delft University ───────────────────────────────────────
    (re.compile(r'\bTU\s+Delft\b|\bDelft\s+University\s+of\s+Technology\b', re.I),
     'TU Delft'),

    # ── KIT ───────────────────────────────────────────────────────────────
    (re.compile(r'Karlsruhe\s+Institute\s+of\s+Technology|\bKIT\b', re.I),
     'Karlsruhe Institute of Technology'),

    # ── Graz University of Technology (TU Graz) ───────────────────────────
    (re.compile(r'\bTU\s+Graz\b|Graz\s+University\s+of\s+Technology', re.I),
     'Graz University of Technology'),

    # ── KAIST ─────────────────────────────────────────────────────────────
    (re.compile(r'^KAIST\b|\bKAIST\b|Korea\s+Advanced\s+Institute\s+of\s+Science', re.I),
     'KAIST'),

    # ── NUS ───────────────────────────────────────────────────────────────
    (re.compile(r'National\s+University\s+of\s+Singapore|^NUS\b', re.I),
     'National University of Singapore'),

    # ── NTU Singapore vs Taiwan ───────────────────────────────────────────
    (re.compile(r'Nanyang\s+Technological\s+University|\bNTU\b.*Singapore', re.I),
     'Nanyang Technological University'),

    # ── SUTD ──────────────────────────────────────────────────────────────
    (re.compile(r'Singapore\s+University\s+of\s+Technology\s+and\s+Design|\bSUTD\b', re.I),
     'Singapore University of Technology and Design'),

    # ── HKUST ─────────────────────────────────────────────────────────────
    (re.compile(r'Hong\s+Kong\s+University\s+of\s+Science\s+and\s+Technology|\bHKUST\b', re.I),
     'Hong Kong University of Science and Technology'),

    # ── CUHK ──────────────────────────────────────────────────────────────
    (re.compile(r'Chinese\s+University\s+of\s+Hong\s+Kong|\bCUHK\b', re.I),
     'Chinese University of Hong Kong'),

    # ── Oregon State (case fix) ───────────────────────────────────────────
    (re.compile(r'Oregon\s+State\s+[Uu]niversity', re.I),
     'Oregon State University'),

    # ── Georgia Tech ──────────────────────────────────────────────────────
    (re.compile(r'Georgia\s+Institute\s+of\s+Technology|Georgia\s+Tech|\bGaTech\b', re.I),
     'Georgia Institute of Technology'),

    # ── Purdue University ────────────────────────────────────────────────
    (re.compile(r'\bPurdue\b|Purdue\s+University', re.I),
     'Purdue University'),

    # ── CMU ───────────────────────────────────────────────────────────────
    (re.compile(r'Carnegie\s+Mellon\s+University|\bCMU\b', re.I),
     'Carnegie Mellon University'),

    # ── Microsoft Research ───────────────────────────────────────────────
    (re.compile(r'Microsoft\s+Research(\s+Asia|\s+Cambridge|\s+Redmond|\s+India)?|\bMSR\b', re.I),
     'Microsoft Research'),

    # ── USTC ──────────────────────────────────────────────────────────────
    (re.compile(r'University\s+of\s+Science\s+and\s+Technology\s+of\s+China|\bUSTC\b', re.I),
     'University of Science and Technology of China'),

    # ── SMU Singapore ─────────────────────────────────────────────────────
    (re.compile(r'Singapore\s+Management\s+University', re.I),
     'Singapore Management University'),
]


def _normalize_affiliation(affiliation: str) -> str:
    """Normalize affiliation string to a canonical form.

    Strategy:
    1. Try each regex rule; if one matches, return its canonical name.
    2. Otherwise, strip department / school / lab details that come after a
       comma following the core university name.  E.g.
       "Tsinghua University, School of Software, Beijing, China"
       → "Tsinghua University"
    """
    if not affiliation:
        return ''
    aff = affiliation.strip()
    if not aff:
        return ''

    # 1. Apply explicit pattern rules
    for pat, canonical in _AFFILIATION_RULES:
        if pat.search(aff):
            return canonical

    # 2. Generic: strip sub-unit details after the university name
    #    Match "<Name> University" or "University of <Name>" then drop the rest.
    m = re.match(
        r'((?:The\s+)?(?:University|Universität|Universidade|Università|Université)'
        r"\s+(?:of\s+)?[\w''\-\–\—.]+(?:\s+[\w''\-\–\—.]+){0,4}?)"
        r'\s*[,(]',
        aff,
        re.IGNORECASE,
    )
    if m:
        core = m.group(1).strip()
        # Keep it only if the core is long enough to be meaningful
        if len(core) > 10:
            return core

    # Same for "<Name> University" pattern (e.g. "Tsinghua University, ...")
    m = re.match(
        r"([\w''\-\–\—.]+(?:\s+[\w''\-\–\—.]+){0,4}?\s+"
        r'(?:University|Institute|Universität|Polytechnic|College))'
        r'\s*[,(]',
        aff,
        re.IGNORECASE,
    )
    if m:
        core = m.group(1).strip()
        if len(core) > 10:
            return core

    return aff


def _normalize_name(name: str) -> str:
    """Normalise a name for cross-dataset matching.

    Steps: NFKD unicode → lower-case → strip DBLP disambiguation suffix →
    strip single-letter initials → collapse whitespace → strip.
    """
    name = unicodedata.normalize('NFKD', name)
    name = re.sub(r'[\t\n\r]+', ' ', name)  # tabs/newlines → space
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
            affiliation=_normalize_affiliation((a.get('affiliation', '') or m.get('affiliation', '')) if m else a.get('affiliation', '')),
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
            affiliation=_normalize_affiliation(m.get('affiliation', '')),
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
# Artifact badges (additive – each level adds 1 pt, max 3 per artifact):
#   Available = 1 pt,  +Functional = +1 pt (total 2),  +Reproducible = +1 pt (total 3)
# AE service:  Each membership = 3,  Each chair role = +2  (on top of membership)
W_AVAILABLE    = 1
W_FUNCTIONAL   = 1   # additional point for functional badge
W_REPRODUCIBLE = 1   # additional point for reproducible badge
W_AE_MEMBERSHIP = 3
W_AE_CHAIR      = 2   # bonus on top of membership


def _build_entry(*, name, affiliation, artifacts, total_papers, artifact_rate,
                 ae_memberships, chair_count, conferences, years,
                 badges_available, badges_functional, badges_reproducible) -> dict:
    """Build a single combined-ranking entry dict with weighted scoring.

    Scoring (additive – each badge level adds 1 pt, max 3 per artifact):
      artifact_score = available*1 + functional*1 + reproducible*1
      ae_score       = memberships*3  + chairs*2
      combined_score = artifact_score + ae_score
    """
    # Compute weighted artifact score (additive: each badge level adds 1 pt)
    artifact_score = (artifacts * W_AVAILABLE
                      + badges_functional * W_FUNCTIONAL
                      + badges_reproducible * W_REPRODUCIBLE)

    # Compute weighted AE score
    ae_score = ae_memberships * W_AE_MEMBERSHIP + chair_count * W_AE_CHAIR

    combined_score = artifact_score + ae_score

    yr_keys = [int(y) for y in years.keys()] if years else []
    
    # Calculate reproducibility rate
    repro_rate = 0
    if badges_available > 0:
        repro_rate = int(round((badges_reproducible / badges_available) * 100))
    
    # Sanitise display name: replace tabs/newlines with spaces, collapse runs
    name = re.sub(r'[\t\n\r]+', ' ', name)
    name = re.sub(r'  +', ' ', name).strip()

    return {
        'name': name,
        'affiliation': affiliation,
        'artifacts': artifacts,
        'artifact_score': artifact_score,
        'total_papers': total_papers,
        'artifact_rate': artifact_rate,
        'repro_rate': repro_rate,
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
    # With additive scoring (each badge level=+1, max 3 per artifact,
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
