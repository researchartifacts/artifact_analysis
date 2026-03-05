#!/usr/bin/env python3
"""Generate search_data.json by merging artifacts.json, paper_authors_map.json, and authors.json."""

import argparse
import json
import os
import re


def normalize_title(t: str) -> str:
    return re.sub(r'[^a-z0-9]', '', t.lower())


def generate_search_data(data_dir: str) -> list:
    assets_data = os.path.join(data_dir, 'assets', 'data')

    with open(os.path.join(assets_data, 'artifacts.json')) as f:
        artifacts = json.load(f)

    pa_path = os.path.join(assets_data, 'paper_authors_map.json')
    paper_authors = []
    if os.path.exists(pa_path):
        with open(pa_path) as f:
            paper_authors = json.load(f)

    authors_path = os.path.join(assets_data, 'authors.json')
    authors_data = []
    if os.path.exists(authors_path):
        with open(authors_path) as f:
            authors_data = json.load(f)

    # Build author -> affiliation lookup
    author_affiliation = {}
    for a in authors_data:
        author_affiliation[a['name']] = a.get('affiliation', '')
        if a.get('display_name'):
            author_affiliation[a['display_name']] = a.get('affiliation', '')

    # Build paper_authors lookup by normalized title
    pa_lookup = {}
    for pa in paper_authors:
        key = normalize_title(pa['title'])
        pa_lookup[key] = pa

    # Merge
    merged = []
    for art in artifacts:
        key = normalize_title(art['title'])
        pa = pa_lookup.get(key, {})
        authors_list = pa.get('authors', [])
        clean_authors = [re.sub(r'\s+\d{4}$', '', a) for a in authors_list]
        affiliations = sorted({
            author_affiliation[a]
            for a in authors_list
            if author_affiliation.get(a)
        })

        doi_url = pa.get('doi_url', '')

        entry = {
            'title': art['title'].strip(),
            'conference': art['conference'],
            'category': art['category'],
            'year': art['year'],
            'badges': art['badges'],
            'repository_url': art.get('repository_url', ''),
            'artifact_url': art.get('artifact_url', ''),
            'doi_url': doi_url,
            'authors': clean_authors,
            'affiliations': affiliations,
        }
        if 'artifact_urls' in art:
            entry['artifact_urls'] = art['artifact_urls']
        merged.append(entry)

    merged.sort(key=lambda x: (-x['year'], x['conference'], x['title']))

    out_path = os.path.join(assets_data, 'search_data.json')
    with open(out_path, 'w') as f:
        json.dump(merged, f)

    print(f"search_data.json: {len(merged)} artifacts "
          f"({sum(1 for e in merged if e['authors'])} with authors, "
          f"{sum(1 for e in merged if e['affiliations'])} with affiliations)")
    return merged


def main():
    parser = argparse.ArgumentParser(description='Generate search_data.json')
    parser.add_argument('--data_dir', type=str, required=True,
                        help='Website output directory')
    args = parser.parse_args()
    generate_search_data(args.data_dir)


if __name__ == '__main__':
    main()
