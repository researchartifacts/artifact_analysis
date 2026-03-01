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

class AffiliationFinder:
    """Find researcher affiliations from various sources."""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.session_count = 0
        
    def log(self, msg: str):
        if self.verbose:
            print(f"[AFFIL] {msg}")
    
    def find_affiliation(self, name: str, max_attempts: int = 3) -> Optional[str]:
        """Try multiple sources to find researcher affiliation."""
        
        # Try DBLP first (most reliable)
        affil = self._try_dblp(name)
        if affil:
            return affil
        
        # Try ORCID (reliable but requires explicit data)
        affil = self._try_orcid(name)
        if affil:
            return affil
        
        # Try University homepages (heuristics)
        affil = self._try_homepage_heuristics(name)
        if affil:
            return affil
        
        return None
    
    def _try_dblp(self, name: str) -> Optional[str]:
        """Query DBLP for author affiliation."""
        self.log(f"Querying DBLP for: {name}")
        
        try:
            # DBLP has a search API and pub pages
            safe_name = quote(name)
            url = f"https://dblp.org/search/publ/api?q={safe_name}&format=json"
            
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status != 200:
                    return None
                
                data = json.loads(response.read().decode())
                
                # Extract affiliations from hits
                if 'result' in data and 'hits' in data['result']:
                    for hit in data['result']['hits'].get('hit', [])[:5]:
                        info = hit.get('info', {})
                        if 'authors' in info:
                            for author in info['authors'].get('author', []):
                                if isinstance(author, dict) and author.get('text', '').lower() == name.lower():
                                    # Found matching author
                                    if 'affiliation' in author:
                                        return author['affiliation']
                
                # Try to parse author pages
                if 'result' in data and 'hits' in data['result']:
                    for hit in data['result']['hits'].get('hit', [])[:3]:
                        url_candidate = hit.get('info', {}).get('url', '')
                        if 'pid' in url_candidate:
                            affil = self._scrape_dblp_author_page(url_candidate)
                            if affil:
                                return affil
        
        except (urllib.error.URLError, json.JSONDecodeError, Exception) as e:
            self.log(f"DBLP lookup failed for {name}: {e}")
        
        return None
    
    def _scrape_dblp_author_page(self, dblp_url: str) -> Optional[str]:
        """Scrape DBLP author page for affiliation."""
        try:
            self.log(f"Scraping DBLP page: {dblp_url}")
            
            with urllib.request.urlopen(dblp_url, timeout=5) as response:
                html = response.read().decode()
                
                # Look for affiliation patterns in HTML
                # DBLP format: <span class="affiliation">...</span> or similar
                affil_match = re.search(r'<span [^>]*class="[^"]*affiliation[^"]*"[^>]*>([^<]+)</span>', html)
                if affil_match:
                    return affil_match.group(1).strip()
                
                # Alternative pattern
                affil_match = re.search(r'(?:Affiliation|affiliation):\s*([^<\n]+)', html)
                if affil_match:
                    return affil_match.group(1).strip()
        
        except Exception as e:
            self.log(f"Failed to scrape {dblp_url}: {e}")
        
        return None
    
    def _try_orcid(self, name: str) -> Optional[str]:
        """Try to find affiliation via ORCID."""
        try:
            self.log(f"Querying ORCID for: {name}")
            safe_name = quote(name)
            url = f"https://pub.orcid.org/v3.0/search?q=family-name+AND+given-name+{safe_name}&rows=5"
            
            with urllib.request.urlopen(url, timeout=5) as response:
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
                        help='Limit number of entries to process (for testing)')
    parser.add_argument('--name', help='Lookup single researcher by name')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    finder = AffiliationFinder(verbose=args.verbose)
    
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
