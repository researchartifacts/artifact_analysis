#!/usr/bin/env python3
"""
Generate and maintain the canonical author index.

The author index is the single source of truth for author identity and
affiliation.  Every author gets a stable integer ID that never changes.

Reads:
  - assets/data/authors.json       (from generate_author_stats — names + display_names)
  - assets/data/author_index.json  (previous index, if any — preserves IDs)

Writes:
  - assets/data/author_index.json

Usage:
  python -m src.generators.generate_author_index --data_dir ../researchartifacts.github.io
"""

import argparse
import json
import os
from datetime import datetime


def load_existing_index(path):
    """Load the previous author index, return (list, name->entry dict, max_id)."""
    if not os.path.exists(path):
        return [], {}, 0
    with open(path, 'r', encoding='utf-8') as f:
        entries = json.load(f)
    by_name = {e['name']: e for e in entries}
    max_id = max((e['id'] for e in entries), default=0)
    return entries, by_name, max_id


def load_authors_json(path):
    """Load authors.json produced by generate_author_stats."""
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def build_index(authors, existing_by_name, max_id):
    """Build a new index, preserving existing IDs and syncing affiliations.

    When an enricher updates authors.json with a new affiliation, we detect
    the change here, update the index entry, and record the old value in
    affiliation_history.

    Returns (index_list, stats_dict).
    """
    today = datetime.now().strftime('%Y-%m-%d')
    index = []
    next_id = max_id + 1
    new_count = 0
    preserved_count = 0
    affiliation_changed_count = 0

    for author in authors:
        name = author.get('name', '')
        if not name:
            continue

        display_name = author.get('display_name', name)
        category = author.get('category', '')
        new_affiliation = author.get('affiliation', '')

        if name in existing_by_name:
            entry = existing_by_name[name].copy()
            # Ensure lists/dicts aren't shared references
            entry['affiliation_history'] = list(entry.get('affiliation_history', []))
            entry['external_ids'] = dict(entry.get('external_ids', {}))

            # Update display_name and category in case they changed
            entry['display_name'] = display_name
            if category:
                entry['category'] = category

            # Detect affiliation change from enrichers
            old_affiliation = entry.get('affiliation', '')
            if new_affiliation and new_affiliation != old_affiliation:
                # Record old value in history (if there was one)
                if old_affiliation:
                    entry['affiliation_history'].append({
                        'affiliation': old_affiliation,
                        'source': entry.get('affiliation_source', ''),
                        'date': entry.get('affiliation_updated', ''),
                    })
                entry['affiliation'] = new_affiliation
                entry['affiliation_updated'] = today
                # We don't know which enricher set it here;
                # enrichers can set affiliation_source directly later
                if not entry.get('affiliation_source'):
                    entry['affiliation_source'] = 'enriched'
                affiliation_changed_count += 1
            preserved_count += 1
        else:
            # New author — assign next ID
            entry = {
                'id': next_id,
                'name': name,
                'display_name': display_name,
                'affiliation': new_affiliation,
                'affiliation_source': '',
                'affiliation_updated': '',
                'affiliation_history': [],
                'external_ids': {},
                'category': category,
            }
            if new_affiliation:
                entry['affiliation_source'] = 'dblp'
                entry['affiliation_updated'] = today

            next_id += 1
            new_count += 1

        index.append(entry)

    # Sort by ID for stable output
    index.sort(key=lambda e: e['id'])

    stats = {
        'total': len(index),
        'preserved': preserved_count,
        'new': new_count,
        'affiliation_changed': affiliation_changed_count,
        'max_id': max(e['id'] for e in index) if index else 0,
        'with_affiliation': sum(1 for e in index if e.get('affiliation')),
    }
    return index, stats


def main():
    parser = argparse.ArgumentParser(
        description='Generate and maintain the canonical author index.'
    )
    parser.add_argument(
        '--data_dir',
        required=True,
        help='Website repo root directory (reads/writes assets/data/)'
    )
    args = parser.parse_args()

    assets_dir = os.path.join(args.data_dir, 'assets', 'data')
    os.makedirs(assets_dir, exist_ok=True)

    index_path = os.path.join(assets_dir, 'author_index.json')
    authors_path = os.path.join(assets_dir, 'authors.json')

    # Load existing index (preserves IDs)
    _, existing_by_name, max_id = load_existing_index(index_path)
    if existing_by_name:
        print(f"Loaded existing index: {len(existing_by_name)} authors, max ID {max_id}")
    else:
        print("No existing index found — creating from scratch")

    # Load authors from generate_author_stats output
    authors = load_authors_json(authors_path)
    if not authors:
        print(f"Error: no authors found in {authors_path}")
        return
    print(f"Loaded {len(authors)} authors from {authors_path}")

    # Build index
    index, stats = build_index(authors, existing_by_name, max_id)

    print(f"Index built: {stats['total']} authors "
          f"({stats['preserved']} preserved, {stats['new']} new, "
          f"{stats['affiliation_changed']} affiliation changes, "
          f"max ID {stats['max_id']})")
    print(f"With affiliation: {stats['with_affiliation']}/{stats['total']} "
          f"({100 * stats['with_affiliation'] / stats['total']:.1f}%)")

    # Write
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    print(f"Written to {index_path}")

    return index


if __name__ == '__main__':
    main()
