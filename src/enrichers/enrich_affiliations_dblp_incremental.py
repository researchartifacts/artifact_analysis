#!/usr/bin/env python3
"""
Incremental DBLP affiliation enrichment with smart prioritization.
- Skips authors that already have affiliations
- Tracks search history to avoid researching
- Prioritizes new authors (search immediately)
- Uses exponential backoff for unsuccessful searches
- Can resume from checkpoint without re-searching
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
from datetime import datetime, timedelta

# Cache configuration
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
CACHE_DIR = os.path.join(REPO_ROOT, '.cache')
CACHE_TTL = 86400 * 90  # 90 days - DBLP affiliations don't change often
SEARCH_HISTORY_FILE = os.path.join(CACHE_DIR, 'dblp_search_history.json')

# Rate limiting
REQUEST_DELAY = 0.2  # seconds between requests

# Exponential backoff configuration (in days)
BACKOFF_DEFAULT = 1      # Search unsuccessful authors again after 1 day
BACKOFF_MULTIPLIER = 2   # Double the backoff each time
BACKOFF_MAX = 30         # Cap at 30 days

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

def load_search_history():
    """Load search history from file."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    if os.path.exists(SEARCH_HISTORY_FILE):
        try:
            with open(SEARCH_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}

def save_search_history(history):
    """Save search history to file."""
    with open(SEARCH_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2)

def should_search_author(author_name, history):
    """
    Determine if an author should be searched based on history.
    
    Returns: (should_search, reason)
    """
    if author_name not in history:
        return True, "new_author"
    
    entry = history[author_name]
    found = entry.get('found', False)
    last_search = entry.get('last_search_ts', 0)
    attempt_count = entry.get('attempt_count', 0)
    
    if found:
        return False, "already_found"
    
    # Calculate backoff period for unsuccessful searches
    backoff_days = min(BACKOFF_DEFAULT * (BACKOFF_MULTIPLIER ** attempt_count), BACKOFF_MAX)
    backoff_seconds = backoff_days * 86400
    
    time_since_search = time.time() - last_search
    
    if time_since_search >= backoff_seconds:
        return True, f"backoff_expired_{backoff_days}d"
    
    return False, f"backoff_active_{int((backoff_seconds - time_since_search) / 3600)}h_left"

def fuzzy_name_match(query_name, result_name):
    """Check if two author names likely match (fuzzy comparison)."""
    def simplify(name):
        # Convert to lowercase, remove initials, keep only letters and spaces
        name = re.sub(r'\d{4}$', '', name).strip().lower()
        # Remove common suffixes
        name = re.sub(r'\s+(jr|sr|phd|ii|iii|iv)\.?', '', name)
        # Remove parenthetical content
        name = re.sub(r'\([^)]*\)', '', name)
        # Normalize whitespace
        name = ' '.join(name.split())
        return name
    
    q_simple = simplify(query_name)
    r_simple = simplify(result_name)
    
    # Check exact match
    if q_simple == r_simple:
        return True
    
    # Check if one is substring of other
    if q_simple in r_simple or r_simple in q_simple:
        return True
    
    # Check if first parts match (last name similarity)
    q_parts = q_simple.split()
    r_parts = r_simple.split()
    if q_parts and r_parts and q_parts[-1] == r_parts[-1]:
        return True
    
    return False

def search_dblp_author(author_name, session, verbose=False):
    """
    Look up an author in the pre-extracted DBLP affiliations.

    Returns a synthetic 'PID' (the author name) when found, preserving the
    caller's control flow.  Falls back to the DBLP API only when the
    extraction cache is unavailable.
    """
    # Clean up author name (remove DBLP suffixes like "0003")
    clean_name = re.sub(r'\s+\d{4}$', '', author_name).strip()

    # Check disk cache first
    cache_key = f"search:{clean_name}"
    cached = _read_cache(cache_key, ttl=CACHE_TTL, namespace='dblp_author')
    if cached is not None:
        if verbose:
            print(f"      Cached PID: {cached if cached else 'not found'}")
        return cached if cached else None

    # --- Try pre-extracted data (no network) ---
    try:
        from ..utils.dblp_extract import load_affiliations
        affiliations = load_affiliations()
        if affiliations:
            if clean_name in affiliations:
                _write_cache(cache_key, clean_name, namespace='dblp_author')
                return clean_name
            lower = clean_name.lower()
            for aname in affiliations:
                if aname.lower() == lower:
                    _write_cache(cache_key, aname, namespace='dblp_author')
                    return aname
            _write_cache(cache_key, '', namespace='dblp_author')
            return None
    except (ImportError, Exception):
        pass  # fall through to API

    if verbose:
        print(f"      Searching DBLP API for: {clean_name}")

    try:
        time.sleep(REQUEST_DELAY)
        api_url = f"https://dblp.org/search/author/api?q={clean_name}&format=json&h=5"
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
            info = hits[0].get('info', {})
            url = info.get('url', '')
            match = re.search(r'/pid/([\w/\-]+)', url)
            if match:
                pid = match.group(1)
                _write_cache(cache_key, pid, namespace='dblp_author')
                return pid
        
        _write_cache(cache_key, '', namespace='dblp_author')
        return None
        
    except requests.RequestException as e:
        print(f"Error searching DBLP for {clean_name}: {e}")
        return None

def fetch_affiliation_from_dblp_page(pid, session, verbose=False):
    """
    Fetch author affiliation.

    When the extraction cache is available *pid* is actually the author name.
    We look it up directly.  Falls back to scraping the DBLP person page.
    """
    # Check disk cache first
    cache_key = f"affil:{pid}"
    cached = _read_cache(cache_key, ttl=CACHE_TTL, namespace='dblp_affil')
    if cached is not None:
        if verbose:
            print(f"      Cached affiliation: {cached if cached else 'not found'}")
        return cached if cached else None

    # --- Try pre-extracted data (no network) ---
    try:
        from ..utils.dblp_extract import load_affiliations
        affiliations = load_affiliations()
        if affiliations:
            affil = affiliations.get(pid)
            if not affil:
                lower = pid.lower()
                for aname, a in affiliations.items():
                    if aname.lower() == lower:
                        affil = a
                        break
            if affil:
                _write_cache(cache_key, affil, namespace='dblp_affil')
                return affil
            _write_cache(cache_key, '', namespace='dblp_affil')
            return None
    except (ImportError, Exception):
        pass  # fall through to web scraping

    person_url = f"https://dblp.org/pid/{pid}.html"
    
    if verbose:
        print(f"      Fetching: {person_url}")
    
    try:
        time.sleep(REQUEST_DELAY)
        response = session.get(person_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for affiliation in JSON-LD or microdata
        affiliation_li = soup.find('li', attrs={'itemprop': 'affiliation'})
        if affiliation_li:
            span = affiliation_li.find('span', attrs={'itemprop': 'name'})
            if span:
                affil = span.get_text(strip=True)
                if affil:
                    _write_cache(cache_key, affil, namespace='dblp_affil')
                    return affil
        
        _write_cache(cache_key, '', namespace='dblp_affil')
        return None
        
    except requests.RequestException as e:
        print(f"Error fetching {person_url}: {e}")
        return None

def enrich_affiliations(authors_data, output_path=None, max_searches=None, verbose=False):
    """
    Incrementally enrich author affiliations using DBLP with smart prioritization.
    
    Args:
        authors_data: List of author dicts from authors.json
        output_path: Path to save enriched data (if None, returns without saving)
        max_searches: Maximum number of searches to perform (for rate limiting)
        verbose: Print detailed progress
    
    Returns:
        Tuple of (enriched_authors_data, stats_dict)
    """
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
    
    # Load search history
    history = load_search_history()
    
    stats = {
        'total_authors': len(authors_data),
        'already_has_affiliation': 0,
        'new_authors_to_search': 0,
        'authors_ready_for_retry': 0,
        'authors_in_backoff': 0,
        'searches_performed': 0,
        'affiliations_found': 0,
        'new_affiliations': 0,
    }
    
    enriched_data = []
    
    print(f"Total authors: {stats['total_authors']}")
    
    # Categorize authors
    to_search = []
    
    for author in authors_data:
        name = author.get('name', '')
        affiliation = author.get('affiliation', '')
        
        # Skip if already has good affiliation
        if affiliation and affiliation not in ['Unknown', ''] and not affiliation.startswith('_'):
            stats['already_has_affiliation'] += 1
            enriched_data.append(author)
            continue
        
        # Check if should search
        should_search, reason = should_search_author(name, history)
        
        if should_search:
            if reason == 'new_author':
                stats['new_authors_to_search'] += 1
                priority = 0  # High priority (new)
            else:  # backoff_expired
                stats['authors_ready_for_retry'] += 1
                priority = 1  # Lower priority (retry)
            to_search.append((priority, name, author))
        else:
            stats['authors_in_backoff'] += 1
            enriched_data.append(author)
    
    # Sort by priority (new authors first), then randomly within priority
    to_search.sort(key=lambda x: x[0])
    
    print(f"Already have affiliation: {stats['already_has_affiliation']}")
    print(f"New authors to search: {stats['new_authors_to_search']}")
    print(f"Ready for retry: {stats['authors_ready_for_retry']}")
    print(f"In backoff period: {stats['authors_in_backoff']}")
    print(f"Total to search now: {len(to_search)}")
    
    if len(to_search) == 0:
        print("\nNo new authors to search. All have affiliations or are in backoff period.")
        return authors_data, stats
    
    print("\nStarting incremental DBLP enrichment...\n")
    
    for priority, name, author in to_search:
        if max_searches and stats['searches_performed'] >= max_searches:
            print(f"\nReached max searches limit ({max_searches})")
            enriched_data.append(author)
            continue
        
        stats['searches_performed'] += 1
        
        # Progress indicator
        if stats['searches_performed'] % 10 == 0 or verbose:
            found_rate = stats['affiliations_found'] / stats['searches_performed'] * 100 if stats['searches_performed'] > 0 else 0
            print(f"  [{stats['searches_performed']}/{len(to_search)}] Found: {stats['affiliations_found']} ({found_rate:.1f}%)")
        
        if verbose:
            print(f"    Searching: {name}")
        
        # Search for author's PID
        pid = search_dblp_author(name, session, verbose=verbose)
        found_affil = False
        
        if pid:
            if verbose:
                print(f"      Found PID: {pid}")
            
            # Fetch affiliation from person page
            affil = fetch_affiliation_from_dblp_page(pid, session, verbose=verbose)
            
            if affil:
                stats['affiliations_found'] += 1
                stats['new_affiliations'] += 1
                author['affiliation'] = affil
                found_affil = True
                print(f"    ✓ {name} → {affil}")
            elif verbose:
                print(f"      No affiliation found on page")
        
        # Update search history
        if name not in history:
            history[name] = {'attempt_count': 0}
        
        history[name]['last_search_ts'] = time.time()
        history[name]['found'] = found_affil
        history[name]['attempt_count'] = history[name].get('attempt_count', 0) + 1
        
        enriched_data.append(author)
    
    # Save updated history
    save_search_history(history)
    
    # Save if output path provided
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(enriched_data, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Enriched data saved to {output_path}")
    
    print(f"\n📊 Summary:")
    print(f"   Searches performed: {stats['searches_performed']}")
    print(f"   New affiliations found: {stats['new_affiliations']}")
    print(f"   Success rate: {stats['affiliations_found']}/{stats['searches_performed']} ({stats['affiliations_found']/stats['searches_performed']*100:.1f}% if stats['searches_performed'] > 0 else 0)")
    print(f"   Search history saved: {SEARCH_HISTORY_FILE}")
    
    return enriched_data, stats

def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Incremental DBLP affiliation enrichment with smart prioritization'
    )
    parser.add_argument(
        '--data_dir',
        default='../researchartifacts.github.io',
        help='Path to website data directory'
    )
    parser.add_argument(
        '--max_searches',
        type=int,
        default=None,
        help='Maximum number of searches to perform (for rate limiting)'
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
    parser.add_argument(
        '--clear_history',
        action='store_true',
        help='Clear search history and start fresh'
    )
    
    args = parser.parse_args()
    
    if args.clear_history and os.path.exists(SEARCH_HISTORY_FILE):
        os.remove(SEARCH_HISTORY_FILE)
        print(f"Cleared search history: {SEARCH_HISTORY_FILE}")
    
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
        max_searches=args.max_searches,
        verbose=args.verbose
    )
    
    return stats

if __name__ == '__main__':
    main()
