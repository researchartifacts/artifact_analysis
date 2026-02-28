#!/usr/bin/env python3
"""
Generate prolific artifact author statistics by matching artifact papers with DBLP.
This script requires downloading the DBLP XML file first (~3GB compressed).
Download from: https://dblp.org/xml/dblp.xml.gz
"""

import json
import yaml
import argparse
import os
from collections import defaultdict
from datetime import datetime
import lxml.etree as ET
from gzip import GzipFile
import re

# Conference categorization is derived from the source (sys vs sec artifacts)
# and stored in the 'category' field of each artifact by generate_statistics.py

# Mapping from DBLP booktitle substrings to our conference identifiers.
# Used to count ALL papers by an author at tracked conferences (not just artifact papers).
DBLP_VENUE_MAP = {
    'EuroSys': 'EUROSYS',
    'SOSP': 'SOSP',
    'SC ': 'SC',           # space after to avoid false matches
    'Supercomputing': 'SC',
    'FAST': 'FAST',
    'USENIX Security': 'USENIXSEC',
    'ACSAC': 'ACSAC',
    'PoPETs': 'PETS',
    'Privacy Enhancing': 'PETS',
    'CHES': 'CHES',
    'NDSS': 'NDSS',
    'WOOT': 'WOOT',
    'SysTEX': 'SYSTEX',
    'OSDI': 'OSDI',
    'ATC': 'ATC',
    'NSDI': 'NSDI',
}

def venue_to_conference(booktitle):
    """Map a DBLP booktitle to our conference identifier, or None."""
    if not booktitle:
        return None
    for pattern, conf in DBLP_VENUE_MAP.items():
        if pattern in booktitle:
            return conf
    return None

def normalize_title(title):
    """Normalize title for matching"""
    if not title:
        return ""
    # Remove punctuation and convert to lowercase
    normalized = re.sub(r'[^\w\s]', '', title.lower())
    # Remove extra whitespace
    normalized = ' '.join(normalized.split())
    return normalized

def load_artifacts(data_dir):
    """Load artifacts from generated data file"""
    artifacts_path = os.path.join(data_dir, 'assets/data/artifacts.json')
    if not os.path.exists(artifacts_path):
        print(f"Error: {artifacts_path} not found")
        print("Please run generate_statistics.py first")
        return None
    
    with open(artifacts_path, 'r') as f:
        artifacts = json.load(f)
    
    return artifacts

def extract_paper_titles(artifacts):
    """Extract unique paper titles from artifacts"""
    titles = set()
    title_to_artifact = {}
    
    for artifact in artifacts:
        title = artifact.get('title', '')
        if title and title != 'Unknown':
            normalized = normalize_title(title)
            titles.add(normalized)
            # Keep mapping for metadata
            if normalized not in title_to_artifact:
                title_to_artifact[normalized] = artifact
    
    # Found {len(titles)} unique paper titles
    return titles, title_to_artifact

def parse_dblp_for_authors(dblp_file, paper_titles, title_to_artifact):
    """
    Parse DBLP XML and find authors for artifact papers.
    Also collects ALL papers at tracked conference venues so we can later
    compute per-author total-publication counts (the denominator for
    artifact rate).
    
    Args:
        dblp_file: Path to dblp.xml.gz file
        paper_titles: Set of normalized paper titles to find
        title_to_artifact: Mapping from title to artifact metadata
    
    Returns:
        Tuple of:
          - List of papers with author information (artifact papers)
          - Dict mapping (author, conference) -> set of normalized titles
            for ALL papers at tracked venues (venue_papers)
          - Dict mapping author_name -> affiliation string (from DBLP <www> entries)
    """
    if not os.path.exists(dblp_file):
        print(f"Error: DBLP file not found: {dblp_file}")
        print("Please download from: https://dblp.org/xml/dblp.xml.gz")
        return [], {}, {}
    
    print("Parsing DBLP XML file (this may take several minutes)...")
    
    papers_found = []
    titles_to_find = paper_titles.copy()
    # (author_name, conference) -> {year: set of normalized_title}
    venue_papers = defaultdict(lambda: defaultdict(set))
    # author_name -> affiliation (extracted from DBLP <www> person records)
    affiliations = {}
    
    try:
        dblp_stream = GzipFile(filename=dblp_file)
        iteration = 0
        
        for event, elem in ET.iterparse(
            dblp_stream,
            events=('end',),
            tag=('inproceedings', 'article', 'www'),
            load_dtd=True,
            recover=True,
            huge_tree=True
        ):
            # --- Extract affiliations from <www> person records ---
            if elem.tag == 'www':
                authors_elems = elem.findall('author')
                if authors_elems:
                    # Extract affiliation from <note type="affiliation">
                    affil = None
                    for note in elem.findall('note'):
                        if note.get('type') == 'affiliation' and note.text:
                            affil = note.text.strip()
                            break
                    if affil:
                        # Store affiliation under ALL name variants (aliases)
                        # DBLP <www> entries list canonical name first, then aliases
                        for author_elem in authors_elems:
                            name = author_elem.text
                            if name and name not in affiliations:
                                affiliations[name] = affil
                elem.clear()
                continue

            title = elem.findtext('title')
            if title:
                # Remove trailing period from DBLP titles
                normalized = normalize_title(title.rstrip('.'))
                
                # --- Track all papers at tracked conference venues ---
                booktitle = elem.findtext('booktitle') or elem.findtext('journal') or ''
                mapped_conf = venue_to_conference(booktitle)
                if mapped_conf:
                    paper_year_str = elem.findtext('year')
                    paper_year = int(paper_year_str) if paper_year_str else None
                    authors = [a.text for a in elem.findall('author') if a.text]
                    for author in authors:
                        if paper_year:
                            venue_papers[(author, mapped_conf)][paper_year].add(normalized)
                        else:
                            venue_papers[(author, mapped_conf)][0].add(normalized)
                
                # --- Match artifact titles (existing behaviour) ---
                if normalized in titles_to_find:
                    if not mapped_conf:
                        authors = [a.text for a in elem.findall('author') if a.text]
                    year = elem.findtext('year')
                    venue = booktitle
                    
                    artifact_meta = title_to_artifact.get(normalized, {})
                    
                    paper_info = {
                        'title': title,
                        'normalized_title': normalized,
                        'authors': authors,
                        'year': int(year) if year else artifact_meta.get('year'),
                        'venue': venue,
                        'conference': artifact_meta.get('conference', ''),
                        'category': artifact_meta.get('category', 'unknown'),
                        'badges': artifact_meta.get('badges', [])
                    }
                    
                    papers_found.append(paper_info)
                    titles_to_find.remove(normalized)
            
            iteration += 1
            elem.clear()  # Clear to save memory
        
        dblp_stream.close()
        
    except Exception as e:
        print(f"Error parsing DBLP: {e}")
        return papers_found, venue_papers, affiliations
    
    if titles_to_find:
        print(f"Warning: {len(titles_to_find)} papers not found in DBLP")
    
    total_venue = sum(len(t) for ydict in venue_papers.values() for t in ydict.values())
    print(f"Total artifact papers matched: {len(papers_found)}")
    print(f"Total papers tracked at conference venues: {total_venue} (author-paper pairs)")
    print(f"Total DBLP affiliations extracted: {len(affiliations)}")
    return papers_found, venue_papers, affiliations

def aggregate_author_statistics(papers, venue_papers=None, affiliations=None):
    """Calculate statistics per author.
    
    Args:
        papers: list of artifact papers with author info
        venue_papers: optional dict (author, conference)->set(titles)
                      of ALL papers at tracked conferences
        affiliations: optional dict author_name -> affiliation string
    """
    if venue_papers is None:
        venue_papers = {}
    if affiliations is None:
        affiliations = {}
    
    author_stats = defaultdict(lambda: {
        'name': '',
        'artifact_count': 0,
        'papers': [],
        'conferences': set(),
        'years': set(),
        'badges': {
            'available': 0,
            'functional': 0,
            'reproducible': 0
        }
    })
    
    for paper in papers:
        for author in paper['authors']:
            stats = author_stats[author]
            stats['name'] = author
            stats['artifact_count'] += 1
            stats['papers'].append({
                'title': paper['title'],
                'conference': paper['conference'],
                'year': paper['year'],
                'badges': paper['badges'],
                'category': paper.get('category', 'unknown')
            })
            stats['conferences'].add(paper['conference'])
            stats['years'].add(paper['year'])
            
            badge_list = paper['badges']
            if isinstance(badge_list, str):
                badge_list = [b.strip() for b in badge_list.split(',')]
            for badge in badge_list:
                badge_lower = badge.lower()
                if 'available' in badge_lower:
                    stats['badges']['available'] += 1
                elif 'functional' in badge_lower:
                    stats['badges']['functional'] += 1
                elif 'reproduc' in badge_lower:
                    stats['badges']['reproducible'] += 1
    
    # Convert to list and add computed fields
    authors_list = []
    current_year = datetime.now().year
    
    # Track category-specific authors
    systems_authors = set()
    security_authors = set()
    cross_domain_authors = set()
    
    for author, stats in author_stats.items():
        years_sorted = sorted(stats['years'])
        recent_count = sum(1 for y in stats['years'] if y >= current_year - 3)
        
        # Determine author category based on paper categories
        confs = list(stats['conferences'])
        paper_categories = set(p.get('category', 'unknown') for p in stats['papers'])
        has_systems = 'systems' in paper_categories
        has_security = 'security' in paper_categories
        
        if has_systems and has_security:
            category = 'both'
            cross_domain_authors.add(author)
            systems_authors.add(author)
            security_authors.add(author)
        elif has_systems:
            category = 'systems'
            systems_authors.add(author)
        elif has_security:
            category = 'security'
            security_authors.add(author)
        else:
            category = 'unknown'
        
        # --- Compute total papers at tracked conferences (per-conf per-year) ---
        total_papers_set = set()
        total_papers_by_conf = {}
        total_papers_by_conf_year = {}
        for conf in stats['conferences']:
            year_dict = venue_papers.get((author, conf), {})
            conf_titles = set()
            conf_year_counts = {}
            for yr, titles in year_dict.items():
                conf_titles |= titles
                conf_year_counts[yr] = len(titles)
            total_papers_set |= conf_titles
            total_papers_by_conf[conf] = len(conf_titles)
            total_papers_by_conf_year[conf] = conf_year_counts
        # Also check conferences the author didn't have artifacts at but
        # did publish at (from DBLP venue scan)
        for (a, c), year_dict in venue_papers.items():
            if a == author and c not in total_papers_by_conf:
                conf_titles = set()
                conf_year_counts = {}
                for yr, titles in year_dict.items():
                    conf_titles |= titles
                    conf_year_counts[yr] = len(titles)
                total_papers_set |= conf_titles
                total_papers_by_conf[c] = len(conf_titles)
                total_papers_by_conf_year[c] = conf_year_counts
        total_papers = len(total_papers_set) if total_papers_set else 0
        
        art_count = stats['artifact_count']
        avail = stats['badges']['available']
        func = stats['badges']['functional']
        repro = stats['badges']['reproducible']
        
        # Artifact rate: % of tracked-conference papers that have an artifact
        artifact_rate = round(art_count / total_papers * 100, 1) if total_papers > 0 else 0.0
        # Reproducibility rate: % of artifact papers with a "reproduced" badge
        repro_rate = round(repro / art_count * 100, 1) if art_count > 0 else 0.0
        # Functional rate: % of artifact papers with a "functional" badge
        functional_rate = round(func / art_count * 100, 1) if art_count > 0 else 0.0
        
        # Look up affiliation from DBLP
        affiliation = affiliations.get(stats['name'], '')

        author_entry = {
            'name': stats['name'],
            'affiliation': affiliation,
            'artifact_count': art_count,
            'total_papers': total_papers,
            'total_papers_by_conf': total_papers_by_conf,
            'total_papers_by_conf_year': total_papers_by_conf_year,
            'artifact_rate': artifact_rate,
            'repro_rate': repro_rate,
            'functional_rate': functional_rate,
            'category': category,
            'conferences': sorted(list(stats['conferences'])),
            'years': years_sorted,
            'year_range': f"{min(years_sorted)}-{max(years_sorted)}" if years_sorted else "",
            'recent_count': recent_count,
            'badges_available': avail,
            'badges_functional': func,
            'badges_reproducible': repro,
            'papers': stats['papers']
        }
        authors_list.append(author_entry)
    
    # Sort by artifact count
    authors_list.sort(key=lambda x: x['artifact_count'], reverse=True)
    
    # Add category breakdown to return
    category_breakdown = {
        'systems_count': len(systems_authors),
        'security_count': len(security_authors),
        'cross_domain_count': len(cross_domain_authors)
    }
    
    return authors_list, category_breakdown

def generate_author_stats(dblp_file, data_dir, output_dir):
    """Main function to generate author statistics"""
    print("Generating author statistics...")
    
    # Load artifacts
    artifacts = load_artifacts(data_dir)
    if not artifacts:
        return None
    
    # Total artifacts: {len(artifacts)}
    
    # Extract titles
    paper_titles, title_to_artifact = extract_paper_titles(artifacts)
    
    # Parse DBLP
    papers_with_authors, venue_papers, affiliations = parse_dblp_for_authors(dblp_file, paper_titles, title_to_artifact)
    
    if not papers_with_authors:
        print("No papers matched in DBLP")
        return None
    
    # Aggregate statistics (pass venue_papers for total-paper counts)
    authors_list, category_breakdown = aggregate_author_statistics(papers_with_authors, venue_papers, affiliations)
    
    # Count affiliation coverage
    with_affil = sum(1 for a in authors_list if a.get('affiliation'))
    print(f"Authors with DBLP affiliation: {with_affil}/{len(authors_list)} ({round(with_affil/len(authors_list)*100, 1) if authors_list else 0}%)")
    
    # Generate summary
    author_summary = {
        'total_authors': len(authors_list),
        'total_papers_matched': len(papers_with_authors),
        'active_last_year': sum(1 for a in authors_list if a['recent_count'] > 0),
        'multi_conference': sum(1 for a in authors_list if len(a['conferences']) > 1),
        'systems_authors': category_breakdown['systems_count'],
        'security_authors': category_breakdown['security_count'],
        'cross_domain_authors': category_breakdown['cross_domain_count'],
        'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')
    }
    
    # Write output files
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(os.path.join(output_dir, '_data'), exist_ok=True)
    os.makedirs(os.path.join(output_dir, 'assets/data'), exist_ok=True)
    
    # YAML for Jekyll (all authors, not truncated)
    with open(os.path.join(output_dir, '_data/authors.yml'), 'w') as f:
        yaml.dump(authors_list, f, default_flow_style=False, allow_unicode=True)
    
    with open(os.path.join(output_dir, '_data/author_summary.yml'), 'w') as f:
        yaml.dump(author_summary, f, default_flow_style=False)
    
    # JSON for download
    with open(os.path.join(output_dir, 'assets/data/authors.json'), 'w') as f:
        json.dump(authors_list, f, indent=2, ensure_ascii=False)
    
    print(f"Author data written to {output_dir} ({len(authors_list)} authors, {len(papers_with_authors)} papers)")
    
    return {'authors': authors_list, 'summary': author_summary}

def main():
    parser = argparse.ArgumentParser(
        description='Generate author statistics from DBLP'
    )
    parser.add_argument(
        '--dblp_file',
        type=str,
        default='dblp.xml.gz',
        help='Path to DBLP XML file (download from https://dblp.org/xml/dblp.xml.gz)'
    )
    parser.add_argument(
        '--data_dir',
        type=str,
        required=True,
        help='Directory containing generated artifacts data'
    )
    parser.add_argument(
        '--output_dir',
        type=str,
        required=True,
        help='Output directory for author statistics'
    )
    
    args = parser.parse_args()
    
    result = generate_author_stats(args.dblp_file, args.data_dir, args.output_dir)
    
    if result:
        s = result['summary']
        print(f"Authors: {s['total_authors']} ({s['total_papers_matched']} papers, {s['multi_conference']} multi-conf)")

if __name__ == '__main__':
    main()
