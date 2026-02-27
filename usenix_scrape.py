#!/usr/bin/env python3
"""
Scrape USENIX conference technical-sessions pages (e.g. FAST, OSDI, ATC)
for paper titles and artifact evaluation badges.

Each USENIX conference publishes a program at:
  https://www.usenix.org/conference/<conf><yy>/technical-sessions

Individual presentation pages may include artifact badge images in a
``field-artifact-evaluated`` div. The badge type is inferred from the
image filename (available, functional, reproduced/reproduced).

Usage examples:
  # Scrape FAST 2025
  python usenix_scrape.py --conference fast --years 2025

  # Scrape FAST 2024 and 2025
  python usenix_scrape.py --conference fast --years 2024,2025

  # Scrape multiple conferences
  python usenix_scrape.py --conference fast,osdi --years 2024,2025

  # Output as YAML suitable for the pipeline
  python usenix_scrape.py --conference fast --years 2025 --format yaml
"""

import argparse
import re
import sys
import time
import json
import yaml
import requests
from bs4 import BeautifulSoup
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from sys_sec_scrape import _read_cache, _write_cache, CACHE_TTL

BASE_URL = "https://www.usenix.org"

# Map full year → short suffix used in USENIX URLs (e.g. 2025 → "25")
def _year_suffix(year):
    return str(year)[2:]


def get_session(session=None):
    """Return a requests.Session, optionally reusing an existing one."""
    if session is not None:
        return session
    s = requests.Session()
    s.headers.update({
        'User-Agent': 'ResearchArtifacts/1.0 (artifact statistics collection)'
    })
    return s


def scrape_presentation_links(conference, year, session=None):
    """
    Scrape the technical-sessions page for a USENIX conference and return
    a list of unique presentation paths (e.g. /conference/fast25/presentation/satija).
    """
    sess = get_session(session)
    suffix = _year_suffix(year)
    url = f"{BASE_URL}/conference/{conference}{suffix}/technical-sessions"

    print(f"  Fetching program: {url}", file=sys.stderr)
    cached = _read_cache(url, ttl=CACHE_TTL, namespace='usenix')
    if cached is not None:
        links = cached
        print(f"  Found {len(links)} unique presentation pages (cached)", file=sys.stderr)
        return links

    resp = sess.get(url, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, 'html.parser')

    # Find all links to presentation pages
    prefix = f"/conference/{conference}{suffix}/presentation/"
    links = set()
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        if href.startswith(prefix):
            links.add(href)

    result = sorted(links)
    _write_cache(url, result, namespace='usenix')
    print(f"  Found {len(result)} unique presentation pages", file=sys.stderr)
    return result


def scrape_paper_page(path, session=None):
    """
    Scrape a single USENIX presentation page and extract:
      - title
      - authors (text)
      - artifact evaluation badges (from badge images)
      - paper PDF URL

    Returns a dict or None if the page is not a research paper.
    """
    sess = get_session(session)
    url = f"{BASE_URL}{path}"

    # Check cache first
    cached = _read_cache(url, ttl=CACHE_TTL, namespace='usenix_paper')
    if cached is not None:
        return cached  # dict or None

    resp = sess.get(url, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, 'html.parser')

    # Extract title from <h1> with id "page-title" or class "page__title"
    title_el = soup.find('h1', id='page-title') or soup.find('h1', class_='page__title')
    if not title_el:
        _write_cache(url, None, namespace='usenix_paper')
        return None
    title = title_el.get_text(strip=True)

    # Skip non-paper entries (keynotes, panels, etc.)
    skip_prefixes = ('keynote', 'panel', 'workshop', 'tutorial', 'honoring',
                     'break', 'lunch', 'closing', 'opening', 'reception',
                     'poster session', 'work-in-progress')
    if any(title.lower().startswith(p) for p in skip_prefixes):
        _write_cache(url, None, namespace='usenix_paper')
        return None

    # Extract authors
    authors_div = soup.find('div', class_=re.compile(r'field-name-field-paper-people-text'))
    authors = ''
    if authors_div:
        authors = authors_div.get_text(strip=True)

    # Extract artifact badges
    badges = []
    artifact_div = soup.find('div', class_=re.compile(r'field-name-field-artifact-evaluated'))
    if artifact_div:
        for img in artifact_div.find_all('img'):
            src = img.get('src', '').lower()
            if 'available' in src:
                badges.append('available')
            elif 'functional' in src:
                badges.append('functional')
            elif 'reproduced' in src or 'replicated' in src:
                badges.append('reproduced')

    # Extract paper PDF URL
    paper_url = ''
    pdf_div = soup.find('div', class_=re.compile(r'field-name-field-final-paper-pdf'))
    if pdf_div:
        pdf_link = pdf_div.find('a', href=True)
        if pdf_link:
            paper_url = pdf_link['href']
            if paper_url.startswith('/'):
                paper_url = BASE_URL + paper_url

    result = {
        'title': title,
        'authors': authors,
        'badges': badges,
        'paper_url': paper_url,
        'presentation_url': url,
    }
    _write_cache(url, result, namespace='usenix_paper')
    return result


def scrape_conference_year(conference, year, session=None, max_workers=4, delay=0.5):
    """
    Scrape all papers and badges for a conference/year combination.

    Args:
        conference: Conference short name (e.g. 'fast')
        year: Full year (e.g. 2025)
        session: Optional requests.Session
        max_workers: Number of parallel requests for paper pages
        delay: Delay between batches of requests (be polite)

    Returns:
        List of artifact dicts with badges
    """
    sess = get_session(session)
    paths = scrape_presentation_links(conference, year, sess)

    if not paths:
        print(f"  No presentation pages found for {conference.upper()} {year}", file=sys.stderr)
        return []

    artifacts = []
    papers_with_badges = 0

    # Scrape paper pages with controlled parallelism
    def _fetch(path):
        time.sleep(delay)  # be polite
        return scrape_paper_page(path, sess)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch, p): p for p in paths}
        for i, future in enumerate(as_completed(futures), 1):
            path = futures[future]
            try:
                result = future.result()
                if result is not None:
                    artifacts.append(result)
                    if result['badges']:
                        papers_with_badges += 1
                    if i % 10 == 0 or i == len(paths):
                        print(f"  Scraped {i}/{len(paths)} pages...", file=sys.stderr)
            except Exception as e:
                print(f"  Error scraping {path}: {e}", file=sys.stderr)

    print(f"  {conference.upper()} {year}: {len(artifacts)} papers, "
          f"{papers_with_badges} with artifact badges", file=sys.stderr)
    return artifacts


def to_pipeline_format(artifacts):
    """
    Convert scraped artifacts to the format used by the existing pipeline
    (matching sys_sec_artifacts_results_scrape.py output format).
    """
    pipeline_artifacts = []
    for a in artifacts:
        if not a['badges']:
            continue  # Only include papers that went through AE
        entry = {
            'title': a['title'],
            'badges': ','.join(a['badges']),
        }
        if a.get('paper_url'):
            entry['paper_url'] = a['paper_url']
        pipeline_artifacts.append(entry)
    return pipeline_artifacts


def main():
    parser = argparse.ArgumentParser(
        description='Scrape USENIX conference pages for paper titles and artifact badges.'
    )
    parser.add_argument(
        '--conference', '-c',
        type=str,
        required=True,
        help='Conference short name(s), comma-separated (e.g. fast, osdi, atc)'
    )
    parser.add_argument(
        '--years', '-y',
        type=str,
        required=True,
        help='Year(s) to scrape, comma-separated (e.g. 2024,2025)'
    )
    parser.add_argument(
        '--format', '-f',
        choices=['json', 'yaml', 'summary'],
        default='summary',
        help='Output format (default: summary)'
    )
    parser.add_argument(
        '--max-workers',
        type=int,
        default=4,
        help='Max parallel requests per conference/year (default: 4)'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=0.3,
        help='Delay in seconds between requests (default: 0.3)'
    )
    parser.add_argument(
        '--all-papers',
        action='store_true',
        help='Include papers without badges in output (default: only badged papers)'
    )

    args = parser.parse_args()

    conferences = [c.strip().lower() for c in args.conference.split(',')]
    years = [int(y.strip()) for y in args.years.split(',')]

    session = get_session()
    all_results = {}

    for conf in conferences:
        for year in years:
            key = f"{conf}{year}"
            print(f"\n{'='*60}", file=sys.stderr)
            print(f"Scraping {conf.upper()} {year}", file=sys.stderr)
            print(f"{'='*60}", file=sys.stderr)

            artifacts = scrape_conference_year(
                conf, year, session,
                max_workers=args.max_workers,
                delay=args.delay
            )

            if args.all_papers:
                all_results[key] = artifacts
            else:
                all_results[key] = to_pipeline_format(artifacts)

    # Output
    if args.format == 'json':
        print(json.dumps(all_results, indent=2))
    elif args.format == 'yaml':
        print(yaml.dump(all_results, default_flow_style=False))
    else:
        # Summary
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        for key, artifacts in sorted(all_results.items()):
            conf_name, year = re.match(r'^([a-z]+)(\d{4})$', key).groups()
            total = len(artifacts)
            if args.all_papers:
                with_badges = sum(1 for a in artifacts if a.get('badges'))
                avail = sum(1 for a in artifacts if 'available' in (a.get('badges') or []))
                func = sum(1 for a in artifacts if 'functional' in (a.get('badges') or []))
                repro = sum(1 for a in artifacts if 'reproduced' in (a.get('badges') or []))
            else:
                with_badges = total
                avail = sum(1 for a in artifacts
                            if 'available' in a.get('badges', ''))
                func = sum(1 for a in artifacts
                           if 'functional' in a.get('badges', ''))
                repro = sum(1 for a in artifacts
                            if 'reproduced' in a.get('badges', ''))
            print(f"  {conf_name.upper()} {year}: {total} papers"
                  f" | {with_badges} with badges"
                  f" (available={avail}, functional={func}, reproduced={repro})")


if __name__ == '__main__':
    main()
