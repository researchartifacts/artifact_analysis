#!/usr/bin/env python3
"""
Enrich author affiliations by fetching data from DBLP person pages.
Uses the DBLP API to search for authors and scrape affiliation from their person pages.
"""

import json
import requests
import time
import re
import hashlib
import os
from pathlib import Path
from bs4 import BeautifulSoup
from collections import defaultdict

# Cache configuration
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache')
CACHE_TTL = 86400 * 90  # 90 days - DBLP affiliations don't change often

# Rate limiting
REQUEST_DELAY = 0.2  # seconds between requests

def _cache_path(key, namespace='default'):
    """Return path to cache file for a given key and namespace."""
    ns_dir = os.path.join(CACHE_DIR, namespace)
    os.makedirs(ns_dir, exist_ok=True)
    hashed = hashlib.sha256(key.encode()).hexdigest()
    return os.path.join(ns_dir, hashed)

def _read_cache(key, ttl=CACHE_TTL, namespace='default'):
    """Return cached value if fresh, else None."""
    path = _cache_path(key, namespace)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            entry = json.load(f)
        if time.time() - entry['ts'] < ttl:
            return entry['body']
    except (json.JSONDecodeError, KeyError, OSError):
        pass
    return None

def _write_cache(key, body, namespace='default'):
    """Write value to cache."""
    path = _cache_path(key, namespace)
    entry = {'ts': time.time(), 'body': body}
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(entry, f)

def search_dblp_author(author_name, session, verbose=False):
    """
    Search for an author in DBLP and return their PID if found.
    Uses the DBLP API search endpoint.
    """
    # Clean up author name (remove DBLP suffixes like "0003")
    clean_name = re.sub(r'\s+\d{4}$', '', author_name).strip()
    
    api_url = f"https://dblp.org/search/author/api?q={clean_name}&format=json&h=5"
    
    # Check cache first
    cache_key = f"search:{clean_name}"
    cached = _read_cache(cache_key, ttl=CACHE_TTL, namespace='dblp_author')
    if cached is not None:
        if verbose:
            print(f"      Cached PID: {cached if cached else 'not found'}")
        return cached if cached else None
    
    if verbose:
        print(f"      Searching DBLP API for: {clean_name}")
    
    try:
        time.sleep(REQUEST_DELAY)
        response = session.get(api_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        hits = data.get('result', {}).get('hits', {}).get('hit', [])
        if not hits:
            _write_cache(cache_key, '', namespace='dblp_author')  # Cache negative result
            return None
        
        # Return the first hit's PID (usually the most relevant)
        for hit in hits:
            info = hit.get('info', {})
            author_name_dblp = info.get('author', '')
            url = info.get('url', '')
            
            # Extract PID from URL (e.g., https://dblp.org/pid/91/800)
            match = re.search(r'/pid/([\w/\-]+)', url)
            if match:
                pid = match.group(1)
                # Check if names roughly match
                if fuzzy_name_match(clean_name, author_name_dblp):
                    _write_cache(cache_key, pid, namespace='dblp_author')
                    return pid
        
        # If no fuzzy match, return first result's PID
        if hits:
            url = hits[0].get('info', {}).get('url', '')
            match = re.search(r'/pid/([\w/\-]+)', url)
            if match:
                pid = match.group(1)
                _write_cache(cache_key, pid, namespace='dblp_author')
                return match.group(1)
    
    except Exception as e:
        print(f"  Error searching for {author_name}: {e}")
    
    _write_cache(cache_key, '', namespace='dblp_author')  # Cache negative result
    return None

def fuzzy_name_match(name1, name2):
    """Simple fuzzy name matching (case-insensitive, ignoring punctuation)."""
    clean1 = re.sub(r'[^\w\s]', '', name1.lower()).strip()
    clean2 = re.sub(r'[^\w\s]', '', name2.lower()).strip()
    
    # Check if one is contained in the other or vice versa
    if clean1 in clean2 or clean2 in clean1:
        return True
    
    # Check if last names match
    parts1 = clean1.split()
    parts2 = clean2.split()
    if parts1 and parts2 and parts1[-1] == parts2[-1]:
        return True
    
    return False

def fetch_affiliation_from_dblp_page(pid, session, verbose=False):
    """
    Fetch affiliation from a DBLP person page.
    """
    url = f"https://dblp.org/pid/{pid}.html"
    
    # Check cache first
    cache_key = f"affiliation:{pid}"
    cached = _read_cache(cache_key, ttl=CACHE_TTL, namespace='dblp_affiliation')
    if cached is not None:
        if verbose:
            print(f"        Cached affiliation: {cached if cached else 'not found'}")
        return cached if cached else None
    
    if verbose:
        print(f"        Fetching: {url}")
    
    try:
        time.sleep(REQUEST_DELAY)
        response = session.get(url, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Look for <li itemprop="affiliation"> containing <span itemprop="name">
        # Example: <li itemprop="affiliation" itemscope itemtype="http://schema.org/Organization">
        #            <em>affiliation:</em> <span itemprop="name">Vrije Universiteit Amsterdam, The Netherlands</span>
        #          </li>
        affiliation_li = soup.find('li', itemprop='affiliation')
        if affiliation_li:
            name_span = affiliation_li.find('span', itemprop='name')
            if name_span and name_span.text:
                affiliation = name_span.text.strip()
                _write_cache(cache_key, affiliation, namespace='dblp_affiliation')
                return affiliation
        
        # Alternative: older format with just <span itemprop="affiliation">
        affiliation_span = soup.find('span', itemprop='affiliation')
        if affiliation_span and affiliation_span.text:
            affiliation = affiliation_span.text.strip()
            _write_cache(cache_key, affiliation, namespace='dblp_affiliation')
            return affiliation
        
        # Alternative: look for affiliation in header section
        header = soup.find('header', id='headline')
        if header:
            affil_div = header.find('div', class_='affiliation')
            if affil_div and affil_div.text:
                affiliation = affil_div.text.strip()
                _write_cache(cache_key, affiliation, namespace='dblp_affiliation')
                return affiliation
        
        if verbose:
            print(f"        Page loaded but no affiliation tags found")
        
        _write_cache(cache_key, '', namespace='dblp_affiliation')  # Cache negative result
    
    except Exception as e:
        if verbose:
            print(f"        Error fetching page: {e}")
        # Don't cache errors - retry next time
    
    return None

def enrich_affiliations(authors_data, output_path=None, max_authors=None, verbose=False):
    """
    Enrich author affiliations by fetching from DBLP.
    
    Args:
        authors_data: List of author dicts from authors.json
        output_path: Path to save enriched data (if None, returns without saving)
        max_authors: Maximum number of authors to process (for testing)
        verbose: Print detailed progress
    
    Returns:
        Tuple of (enriched_authors_data, stats_dict)
    """
    import os
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'ResearchArtifacts-Affiliation-Enricher/1.0 (contact: https://github.com/researchartifacts/artifact_analysis)'
    })
    
    # Add proxy support
    if os.environ.get('https_proxy'):
        session.proxies = {
            'http': os.environ.get('http_proxy', os.environ.get('https_proxy')),
            'https': os.environ.get('https_proxy')
        }
        print(f"Using proxy: {os.environ.get('https_proxy')}")
    
    stats = {
        'total_authors': len(authors_data),
        'initially_missing': 0,
        'looked_up': 0,
        'found_pid': 0,
        'found_affiliation': 0,
        'still_missing': 0
    }
    
    enriched_data = []
    
    # Count initially missing
    for author in authors_data:
        if not author.get('affiliation') or author.get('affiliation') in ['Unknown', ''] or author.get('affiliation', '').startswith('_'):
            stats['initially_missing'] += 1
    
    print(f"Total authors: {stats['total_authors']}")
    print(f"Initially missing affiliations: {stats['initially_missing']}")
    print("\nStarting DBLP enrichment...")
    
    for idx, author in enumerate(authors_data):
        name = author.get('name', '')
        affiliation = author.get('affiliation', '')
        
        # Check if affiliation is missing or unknown
        needs_enrichment = (
            not affiliation or 
            affiliation in ['Unknown', ''] or 
            affiliation.startswith('_')
        )
        
        if needs_enrichment:
            if max_authors and stats['looked_up'] >= max_authors:
                # For testing: stop after max_authors lookups
                enriched_data.append(author)
                continue
            
            stats['looked_up'] += 1
            
            # Progress indicator
            if stats['looked_up'] % 10 == 0 or verbose:
                print(f"  Processed {stats['looked_up']}/{stats['initially_missing']} missing affiliations... (found {stats['found_affiliation']} so far)")
            
            if verbose:
                print(f"    Looking up: {name}")
            
            # Search for author's PID
            pid = search_dblp_author(name, session, verbose=verbose)
            
            if pid:
                stats['found_pid'] += 1
                
                if verbose:
                    print(f"      Found PID: {pid}")
                
                # Fetch affiliation from person page
                affil = fetch_affiliation_from_dblp_page(pid, session, verbose=verbose)
                
                if affil:
                    stats['found_affiliation'] += 1
                    author['affiliation'] = affil
                    print(f"    ✓ {name} -> {affil}")
                elif verbose:
                    print(f"      No affiliation found on page")
        
        enriched_data.append(author)
    
    # Count still missing
    for author in enriched_data:
        if not author.get('affiliation') or author.get('affiliation') in ['Unknown', ''] or author.get('affiliation', '').startswith('_'):
            stats['still_missing'] += 1
    
    # Save if output path provided
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(enriched_data, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Enriched data saved to {output_path}")
    
    return enriched_data, stats

def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Enrich author affiliations from DBLP'
    )
    parser.add_argument(
        '--data_dir',
        default='../researchartifacts.github.io',
        help='Path to website data directory'
    )
    parser.add_argument(
        '--max_authors',
        type=int,
        default=None,
        help='Maximum number of authors to process (for testing)'
    )
    parser.add_argument(
        '--dry_run',
        action='store_true',
        help='Run without saving results'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Print detailed progress'
    )
    
    args = parser.parse_args()
    
    # Load authors.json
    authors_path = Path(args.data_dir) / 'assets' / 'data' / 'authors.json'
    
    if not authors_path.exists():
        print(f"Error: {authors_path} not found")
        return
    
    print(f"Loading {authors_path}...")
    with open(authors_path, 'r', encoding='utf-8') as f:
        authors_data = json.load(f)
    
    # Enrich affiliations
    output_path = None if args.dry_run else authors_path
    enriched_data, stats = enrich_affiliations(
        authors_data,
        output_path=output_path,
        max_authors=args.max_authors,
        verbose=args.verbose
    )
    
    # Print summary
    print("\n" + "="*60)
    print("ENRICHMENT SUMMARY")
    print("="*60)
    print(f"Total authors:              {stats['total_authors']}")
    print(f"Initially missing:          {stats['initially_missing']} ({stats['initially_missing']/stats['total_authors']*100:.1f}%)")
    print(f"Looked up in DBLP:          {stats['looked_up']}")
    print(f"Found DBLP PID:             {stats['found_pid']} ({stats['found_pid']/max(1,stats['looked_up'])*100:.1f}%)")
    print(f"Found affiliation:          {stats['found_affiliation']} ({stats['found_affiliation']/max(1,stats['looked_up'])*100:.1f}%)")
    print(f"Still missing:              {stats['still_missing']} ({stats['still_missing']/stats['total_authors']*100:.1f}%)")
    print(f"Coverage improvement:       {stats['initially_missing'] - stats['still_missing']} affiliations added")
    print(f"New coverage:               {(1 - stats['still_missing']/stats['total_authors'])*100:.1f}%")
    
    if args.dry_run:
        print("\n(Dry run - results not saved)")

if __name__ == '__main__':
    main()
