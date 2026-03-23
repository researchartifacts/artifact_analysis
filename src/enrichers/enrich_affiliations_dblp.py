#!/usr/bin/env python3
"""
Enrich author affiliations using pre-extracted DBLP XML data.

Uses the JSON lookup files produced by ``src.utils.dblp_extract`` instead
of hitting the DBLP web API.
"""

import json
import re
import os
from pathlib import Path


def search_dblp_author(author_name, session=None, verbose=False):
    """Return a key for the author if found in pre-extracted DBLP data.

    Kept as a thin wrapper so callers that do the two-step
    ``search → fetch_affiliation`` dance still work unchanged.
    """
    clean_name = re.sub(r'\s+\d{4}$', '', author_name).strip()
    try:
        from ..utils.dblp_extract import find_affiliation
        if find_affiliation(clean_name) is not None:
            return clean_name
    except (ImportError, Exception):
        pass
    return None


def fetch_affiliation_from_dblp_page(pid, session=None, verbose=False):
    """Return the affiliation for *pid* (which is the author name)."""
    try:
        from ..utils.dblp_extract import find_affiliation
        return find_affiliation(pid)
    except (ImportError, Exception):
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
