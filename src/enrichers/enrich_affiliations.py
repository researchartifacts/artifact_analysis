#!/usr/bin/env python3
"""
Affiliation enrichment tool for ResearchArtifacts.
Attempts to find missing affiliations from DBLP, Google Scholar, and other sources.
"""

import json
import re
import time
import urllib.request
import urllib.error
from typing import Optional, List, Tuple
from urllib.parse import quote
import os

class AffiliationFinder:
    """Find researcher affiliations from various sources."""
    
    def __init__(self, verbose: bool = False, proxy_url: Optional[str] = None):
        self.verbose = verbose
        self.session_count = 0
        self.proxy_url = proxy_url or os.environ.get('HTTP_PROXY', '')
        if self.proxy_url:
            self.log(f"Using proxy: {self.proxy_url}")
        
    def log(self, msg: str):
        if self.verbose:
            print(f"[AFFIL] {msg}")
    
    def _get_opener(self):
        """Create URL opener with optional proxy support."""
        if not self.proxy_url:
            return urllib.request.build_opener()
        
        proxy_handler = urllib.request.ProxyHandler({'http': self.proxy_url, 'https': self.proxy_url})
        return urllib.request.build_opener(proxy_handler)
    
    def find_affiliation(self, name: str, max_attempts: int = 3) -> Optional[str]:
        """Try multiple sources to find researcher affiliation."""
        
        # Try CrossRef first (most reliable for papers)
        affil = self._try_crossref(name)
        if affil:
            return affil
        
        # Try DBLP next
        affil = self._try_dblp(name)
        if affil:
            return affil
        
        # Try ORCID (slower but comprehensive)
        affil = self._try_orcid(name)
        if affil:
            return affil
        
        # Try University homepages (heuristics)
        affil = self._try_homepage_heuristics(name)
        if affil:
            return affil
        
        return None
    
    def _try_crossref(self, name: str) -> Optional[str]:
        """Query CrossRef API for author affiliation from papers."""
        self.log(f"Querying CrossRef for: {name}")
        
        try:
            # Use CrossRef works query
            # Format: https://api.crossref.org/works?query=<query>&rows=<rows>
            safe_name = quote(name)
            url = f"https://api.crossref.org/works?query={safe_name}&rows=10"
            
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'ResearchArtifacts-Affiliation-Enricher/1.0')
            
            opener = self._get_opener()
            with opener.open(req, timeout=10) as response:
                if response.status != 200:
                    return None
                
                data = json.loads(response.read().decode())
                
                # Extract affiliations from works
                if 'message' in data and 'items' in data['message']:
                    for item in data['message']['items']:
                        if 'author' in item:
                            for author in item['author']:
                                # Check if this is our author
                                author_name = f"{author.get('given', '')} {author.get('family', '')}".strip().lower()
                                name_lower = name.lower()
                                # Fuzzy match: at least last name should match
                                family = author.get('family', '').lower()
                                if family and (family in name_lower):
                                    # Found potential matching author
                                    if 'affiliation' in author and author['affiliation']:
                                        # Take first affiliation
                                        aff = author['affiliation'][0]
                                        if isinstance(aff, dict):
                                            org = aff.get('name', '')
                                        else:
                                            org = str(aff)
                                        if org:
                                            return org.strip()
        
        except Exception as e:
            self.log(f"CrossRef lookup failed for {name}: {e}")
        
        return None
    
    def _try_dblp(self, name: str) -> Optional[str]:
        """Look up author affiliation from pre-extracted DBLP XML data."""
        self.log(f"Looking up DBLP affiliation for: {name}")

        try:
            from ..utils.dblp_extract import load_affiliations
            affiliations = load_affiliations()
            if not affiliations:
                self.log("No DBLP extraction cache available")
                return None

            # Exact match first
            if name in affiliations:
                return affiliations[name]

            # Case-insensitive match
            name_lower = name.lower()
            for aname, affil in affiliations.items():
                if aname.lower() == name_lower:
                    return affil

        except (ImportError, Exception) as e:
            self.log(f"DBLP local lookup failed for {name}: {e}")

        return None
    
    def _try_orcid(self, name: str) -> Optional[str]:
        """Try to find affiliation via ORCID."""
        try:
            self.log(f"Querying ORCID for: {name}")
            safe_name = quote(name)
            url = f"https://pub.orcid.org/v3.0/search?q=family-name+AND+given-name+{safe_name}&rows=5"
            
            opener = self._get_opener()
            with opener.open(url, timeout=10) as response:
                if response.status != 200:
                    return None
                
                data = json.loads(response.read().decode())
                
                # Extract affiliations from results
                for result in data.get('result', [])[:3]:
                    result_obj = result.get('result', {})
                    if 'affiliation-group' in result_obj:
                        for aff_group in result_obj['affiliation-group']:
                            if 'affiliation-summary' in aff_group:
                                org = aff_group['affiliation-summary'][0].get('organization', {})
                                if 'name' in org:
                                    return org['name']
        
        except Exception as e:
            self.log(f"ORCID lookup failed: {e}")
        
        return None
    
    def _try_homepage_heuristics(self, name: str) -> Optional[str]:
        """Use heuristics to guess institutional affiliation."""
        # This would require maintaining a database of faculty names by institution
        # For now, we note this as a limitation
        self.log(f"Homepage heuristics not implemented (requires faculty database)")
        return None
    
    def batch_enrichment(self, rankings_file: str, output_file: str, limit: int = None):
        """Batch process rankings file to enrich missing affiliations."""
        
        with open(rankings_file) as f:
            rankings = json.load(f)
        
        to_process = [p for p in rankings if p.get('combined_score', 0) > 5 and not p.get('affiliation', '').strip()]
        
        if limit:
            to_process = to_process[:limit]
        
        print(f"Processing {len(to_process)} entries without affiliation (score > 5)")
        
        enriched_count = 0
        for i, person in enumerate(to_process, 1):
            name = person.get('name', '')
            print(f"\n[{i}/{len(to_process)}] {name} - Score: {person.get('combined_score')}")
            
            affiliation = self.find_affiliation(name)
            
            if affiliation:
                person['affiliation'] = affiliation
                person['affiliation_source'] = 'enriched'
                enriched_count += 1
                print(f"  ✓ Found: {affiliation}")
            else:
                print(f"  ✗ Not found")
            
            # Rate limiting
            time.sleep(1)
        
        print(f"\n✓ Enriched {enriched_count}/{len(to_process)} entries")
        
        # Write back
        with open(output_file, 'w') as f:
            json.dump(rankings, f, indent=2)
        
        print(f"✓ Output written to: {output_file}")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Enrich missing researcher affiliations')
    parser.add_argument('--input', default='researchartifacts.github.io/assets/data/combined_rankings.json',
                        help='Input combined_rankings.json file')
    parser.add_argument('--output', default='combined_rankings_enriched.json',
                        help='Output file with enriched affiliations')
    parser.add_argument('--limit', type=int, default=None,
                        help='Limit number of entries to process (for testing; default: all)')
    parser.add_argument('--name', help='Lookup single researcher by name')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--proxy', help='HTTP proxy URL (can also use HTTP_PROXY env var)')
    
    args = parser.parse_args()
    
    finder = AffiliationFinder(verbose=args.verbose, proxy_url=args.proxy)
    
    if args.name:
        # Single lookup
        affiliation = finder.find_affiliation(args.name)
        if affiliation:
            print(f"✓ {args.name}: {affiliation}")
        else:
            print(f"✗ No affiliation found for: {args.name}")
    else:
        # Batch enrichment
        finder.batch_enrichment(args.input, args.output, limit=args.limit)
