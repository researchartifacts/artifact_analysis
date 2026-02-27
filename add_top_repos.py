#!/usr/bin/env python3
"""Quick script to add top_repos to repo_stats.yml using existing cached data.

Reads the all_results_cache.yml + cached github_stats + authors.yml to compute
top 5 repos per conference with enriched metadata (authors, org, badges, etc.)
without making any API calls.
"""

import hashlib
import json
import os
import re
import yaml
from collections import defaultdict

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache')
WEBSITE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           '..', 'researchartifacts.github.io')


def extract_conference_name(conf_year_str):
    match = re.match(r'^([a-zA-Z]+)(\d{4})$', conf_year_str)
    if match:
        return match.group(1).upper(), int(match.group(2))
    return conf_year_str.upper(), None


def read_cached_github_stats(url):
    """Read cached github stats for a URL without TTL check."""
    ns_dir = os.path.join(CACHE_DIR, 'github_stats')
    hashed = hashlib.sha256(url.encode()).hexdigest()
    path = os.path.join(ns_dir, hashed)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r') as f:
            entry = json.load(f)
        return entry.get('body')
    except (json.JSONDecodeError, KeyError, OSError):
        return None


def build_title_author_map(authors_path):
    """Build mapping from paper title → list of author names."""
    with open(authors_path, 'r') as f:
        authors = yaml.safe_load(f) or []
    title_map = {}
    for author in authors:
        name = author.get('name', '')
        for paper in author.get('papers', []):
            title = paper.get('title', '').strip().rstrip('.')
            if title:
                title_map.setdefault(title, []).append(name)
    return title_map


def build_title_badges_map(all_results):
    """Build mapping from paper title → badges string."""
    title_badges = {}
    for conf_year, artifacts in all_results.items():
        for artifact in artifacts:
            title = artifact.get('title', '').strip().rstrip('.')
            badges = artifact.get('badges', '')
            if title and badges:
                title_badges[title] = badges
    return title_badges


def find_authors_for_title(title, title_author_map):
    """Find authors by exact or prefix match on paper title."""
    title_clean = title.strip().rstrip('.')
    authors = title_author_map.get(title_clean, [])
    if not authors:
        # Try prefix match (titles may be truncated or have minor differences)
        for t, a in title_author_map.items():
            if len(title_clean) >= 25 and t.startswith(title_clean[:25]):
                authors = a
                break
    return authors


def extract_github_org(url, cached_stats):
    """Extract GitHub organization/owner from URL or cached name."""
    if cached_stats and isinstance(cached_stats, dict):
        name = cached_stats.get('name', '')
        if name and '/' in name:
            return name.split('/')[0]
    # Fallback: parse from URL
    try:
        parts = url.split('github.com/')[1].split('/')
        return parts[0] if parts else ''
    except (IndexError, AttributeError):
        return ''


def main():
    # Load artifact data
    cache_path = os.path.join(WEBSITE_DIR, '_data', 'all_results_cache.yml')
    print(f"Loading cached results from {cache_path}...")
    with open(cache_path, 'r') as f:
        all_results = yaml.safe_load(f) or {}
    print(f"Loaded {sum(len(v) for v in all_results.values())} artifacts across "
          f"{len(all_results)} conference-years")

    # Build author and badge lookup maps
    authors_path = os.path.join(WEBSITE_DIR, '_data', 'authors.yml')
    print("Building author lookup from authors.yml...")
    title_author_map = build_title_author_map(authors_path)
    print(f"  {len(title_author_map)} title→author mappings")

    print("Building badge lookup from artifact data...")
    title_badges_map = build_title_badges_map(all_results)
    print(f"  {len(title_badges_map)} title→badges mappings")

    # Collect per-conference GitHub entries from cache
    url_keys = ['repository_url', 'artifact_url', 'github_url', 'second_repository_url']
    by_conf = defaultdict(list)
    seen_urls = set()

    for conf_year, artifacts in all_results.items():
        conf_name, year = extract_conference_name(conf_year)
        if year is None:
            continue

        for artifact in artifacts:
            for url_key in url_keys:
                url = artifact.get(url_key, '')
                if not url or 'github' not in url:
                    continue

                url_normalized = url.rstrip('/')
                if url_normalized in seen_urls:
                    continue
                seen_urls.add(url_normalized)

                stats = read_cached_github_stats(url)
                if stats and isinstance(stats, dict):
                    stars = stats.get('github_stars', 0) or 0
                    forks = stats.get('github_forks', 0) or 0
                    title = artifact.get('title', 'Unknown')

                    # Enrich with authors, org, badges, etc.
                    authors = find_authors_for_title(title, title_author_map)
                    org = extract_github_org(url, stats)
                    badges = title_badges_map.get(title.strip().rstrip('.'), '')
                    pushed_at = stats.get('pushed_at', '')
                    description = stats.get('description', '') or ''
                    language = stats.get('language', '') or ''

                    # Format last activity as YYYY-MM
                    last_active = ''
                    if pushed_at and pushed_at != 'NA':
                        last_active = pushed_at[:7]  # YYYY-MM

                    by_conf[conf_name].append({
                        'title': title,
                        'url': url,
                        'year': year,
                        'stars': stars,
                        'forks': forks,
                        'authors': ', '.join(authors[:5]) + (' et al.' if len(authors) > 5 else ''),
                        'github_org': org,
                        'badges': badges,
                        'last_active': last_active,
                        'description': description[:120] + ('...' if len(description) > 120 else ''),
                        'language': language,
                    })

    print(f"Found GitHub entries for {len(by_conf)} conferences")

    # Load existing repo_stats.yml
    repo_stats_path = os.path.join(WEBSITE_DIR, '_data', 'repo_stats.yml')
    with open(repo_stats_path, 'r') as f:
        repo_stats = yaml.safe_load(f)

    # Add top_repos to each conference
    updated = 0
    for conf_entry in repo_stats['by_conference']:
        conf_name = conf_entry['name']
        if conf_name in by_conf:
            top_repos = sorted(by_conf[conf_name], key=lambda x: x['stars'], reverse=True)[:5]
            conf_entry['top_repos'] = top_repos
            updated += 1
            if top_repos:
                r = top_repos[0]
                print(f"  {conf_name}: {len(by_conf[conf_name])} repos, "
                      f"top: {r['title'][:40]}... ({r['stars']} stars, "
                      f"authors: {r['authors'][:40]})")
        else:
            conf_entry['top_repos'] = []
            print(f"  {conf_name}: no cached GitHub data")

    # Write back
    with open(repo_stats_path, 'w') as f:
        yaml.dump(repo_stats, f, default_flow_style=False, sort_keys=False,
                  allow_unicode=True)
    print(f"\nUpdated {updated} conferences in {repo_stats_path}")


if __name__ == '__main__':
    main()
