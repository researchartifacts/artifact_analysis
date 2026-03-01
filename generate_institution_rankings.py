#!/usr/bin/env python3
"""
Generate institution rankings by aggregating combined ranking data by affiliation.
Creates JSON files for overall, systems, and security institution rankings.
"""

import json
from pathlib import Path
from collections import defaultdict

def load_combined_ranking(path):
    """Load combined ranking JSON."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def aggregate_by_institution(combined_data):
    """Aggregate individual rankings by institution affiliation."""
    inst_data = defaultdict(lambda: {
        'affiliation': '',
        'combined_score': 0,
        'artifacts': 0,
        'badges_functional': 0,
        'badges_reproducible': 0,
        'ae_memberships': 0,
        'chair_count': 0,
        'total_papers': 0,
        'authors': [],
        'conferences': set(),
        'years': defaultdict(int)
    })
    
    for person in combined_data:
        affiliation = person.get('affiliation', '').strip()
        
        # Skip entries with no affiliation or placeholder affiliations
        if not affiliation or affiliation == 'Unknown' or affiliation.startswith('_'):
            affiliation = 'Unknown'
        
        inst = inst_data[affiliation]
        inst['affiliation'] = affiliation
        inst['combined_score'] += person.get('combined_score', 0)
        inst['artifacts'] += person.get('artifacts', 0)
        inst['badges_functional'] += person.get('badges_functional', 0)
        inst['badges_reproducible'] += person.get('badges_reproducible', 0)
        inst['ae_memberships'] += person.get('ae_memberships', 0)
        inst['chair_count'] += person.get('chair_count', 0)
        inst['total_papers'] += person.get('total_papers', 0)
        
        # Store author details for expandable view
        inst['authors'].append({
            'name': person.get('name', ''),
            'combined_score': person.get('combined_score', 0),
            'artifacts': person.get('artifacts', 0),
            'ae_memberships': person.get('ae_memberships', 0),
            'total_papers': person.get('total_papers', 0)
        })
        
        # Aggregate conferences
        if person.get('conferences'):
            inst['conferences'].update(person['conferences'])
        
        # Aggregate years
        if person.get('years'):
            for year, count in person['years'].items():
                inst['years'][year] += count
    
    # Convert to list and calculate derived fields
    institutions = []
    for affiliation, data in inst_data.items():
        # Calculate artifact rate
        artifact_rate = 0
        if data['total_papers'] > 0:
            artifact_rate = round((data['artifacts'] / data['total_papers']) * 100, 1)
        
        # Sort authors by combined_score descending and keep top 20
        authors_sorted = sorted(data['authors'], key=lambda x: x['combined_score'], reverse=True)[:20]
        
        # Only include institutions with meaningful contributions
        if data['combined_score'] >= 3:
            institutions.append({
                'affiliation': data['affiliation'],
                'combined_score': data['combined_score'],
                'artifacts': data['artifacts'],
                'badges_functional': data['badges_functional'],
                'badges_reproducible': data['badges_reproducible'],
                'ae_memberships': data['ae_memberships'],
                'chair_count': data['chair_count'],
                'total_papers': data['total_papers'],
                'artifact_rate': artifact_rate,
                'num_authors': len(data['authors']),
                'top_authors': authors_sorted,
                'conferences': sorted(list(data['conferences'])),
                'years': dict(data['years'])
            })
    
    # Sort by combined_score descending
    institutions.sort(key=lambda x: x['combined_score'], reverse=True)
    
    return institutions

def main():
    """Generate institution ranking JSON files."""
    base_path = Path(__file__).parent
    website_path = base_path.parent / 'researchartifacts.github.io'
    data_dir = website_path / 'assets' / 'data'
    
    # Process overall combined ranking
    print("Processing overall combined ranking...")
    combined_path = data_dir / 'combined_rankings.json'
    if combined_path.exists():
        combined_data = load_combined_ranking(combined_path)
        institutions = aggregate_by_institution(combined_data)
        
        output_path = data_dir / 'institution_rankings.json'
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(institutions, f, indent=2, ensure_ascii=False)
        print(f"  ✓ Generated {output_path} ({len(institutions)} institutions)")
    else:
        print(f"  ✗ {combined_path} not found")
    
    # Process systems combined ranking
    print("Processing systems combined ranking...")
    systems_path = data_dir / 'systems_combined_rankings.json'
    if systems_path.exists():
        systems_data = load_combined_ranking(systems_path)
        systems_institutions = aggregate_by_institution(systems_data)
        
        output_path = data_dir / 'systems_institution_rankings.json'
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(systems_institutions, f, indent=2, ensure_ascii=False)
        print(f"  ✓ Generated {output_path} ({len(systems_institutions)} institutions)")
    else:
        print(f"  ✗ {systems_path} not found")
    
    # Process security combined ranking
    print("Processing security combined ranking...")
    security_path = data_dir / 'security_combined_rankings.json'
    if security_path.exists():
        security_data = load_combined_ranking(security_path)
        security_institutions = aggregate_by_institution(security_data)
        
        output_path = data_dir / 'security_institution_rankings.json'
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(security_institutions, f, indent=2, ensure_ascii=False)
        print(f"  ✓ Generated {output_path} ({len(security_institutions)} institutions)")
    else:
        print(f"  ✗ {security_path} not found")

if __name__ == '__main__':
    main()
