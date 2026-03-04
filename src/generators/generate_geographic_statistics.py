#!/usr/bin/env python3
"""
Generate geographic (country/continent) statistics from institution rankings.
Calculates reproducibility rates, artifact metrics, and other insights by country and continent.
"""

import json
from pathlib import Path
from collections import defaultdict
from statistics import median, mean

# Country to continent mapping
COUNTRY_TO_CONTINENT = {
    'US': 'North America', 'CA': 'North America', 'MX': 'North America',
    'CN': 'Asia', 'JP': 'Asia', 'KR': 'Asia', 'TW': 'Asia', 'IN': 'Asia',
    'SG': 'Asia', 'TH': 'Asia', 'MY': 'Asia', 'ID': 'Asia', 'PH': 'Asia',
    'VN': 'Asia', 'PK': 'Asia', 'BD': 'Asia', 'HK': 'Asia', 'LK': 'Asia',
    'GB': 'Europe', 'DE': 'Europe', 'FR': 'Europe', 'IT': 'Europe', 'ES': 'Europe',
    'NL': 'Europe', 'SE': 'Europe', 'NO': 'Europe', 'DK': 'Europe', 'FI': 'Europe',
    'BE': 'Europe', 'AT': 'Europe', 'CH': 'Europe', 'IE': 'Europe', 'PT': 'Europe',
    'GR': 'Europe', 'CZ': 'Europe', 'HU': 'Europe', 'PL': 'Europe', 'RO': 'Europe',
    'UA': 'Europe', 'RU': 'Europe', 'TR': 'Europe', 'IL': 'Asia', 'SA': 'Asia',
    'AE': 'Asia', 'IR': 'Asia',
    'AU': 'Oceania', 'NZ': 'Oceania',
    'BR': 'South America', 'AR': 'South America', 'CL': 'South America',
    'CO': 'South America', 'PE': 'South America', 'VE': 'South America',
    'ZA': 'Africa', 'EG': 'Africa', 'KE': 'Africa', 'NG': 'Africa', 'MA': 'Africa'
}

# Known institutions by country (same mapping as in institution_ranking_table.html)
KNOWN_INSTITUTIONS_BY_COUNTRY = {
    'US': ['mit', 'stanford', 'berkeley', 'carnegie mellon', 'harvard', 'princeton',
           'yale', 'cornell', 'columbia', 'penn', 'upenn', 'cmu', 'ucsd', 'ucsb',
           'ucla', 'uiuc', 'georgia tech', 'msu', 'michigan', 'caltech', 'purdue',
           'texas austin', 'utexas', 'wisconsin', 'washington', 'google', 'microsoft',
           'amazon', 'apple', 'meta', 'facebook', 'ibm', 'intel', 'cisco', 'oracle',
           'vmware', 'adobe'],
    'GB': ['oxford', 'cambridge', 'imperial', 'ucl', 'london', 'edinburgh', 'manchester',
           'bristol', 'warwick'],
    'CN': ['tsinghua', 'peking', 'fudan', 'shanghai', 'zhejiang', 'nanjing', 'harbin',
           'beijing', 'alibaba', 'tencent', 'bytedance', 'baidu', 'huawei'],
    'CH': ['eth', 'ethz', 'zurich', 'epfl'],
    'DE': ['aachen', 'tu aachen', 'rwth', 'munich', 'bonn', 'heidelberg', 'berlin',
           'darmstadt', 'karlsruhe', 'saarland', 'tu darmstadt'],
    'FR': ['paris', 'sorbonne', 'inria', 'grenoble', 'polytechnique'],
    'NL': ['delft', 'tu delft', 'amsterdam'],
    'SE': ['lund', 'kth', 'göteborg', 'chalmers'],
    'JP': ['tokyo', 'kyoto', 'osaka', 'tohoku'],
    'KR': ['kaist', 'seoul', 'postech'],
    'SG': ['nus', 'ntu singapore', 'sutd'],
    'IN': ['iisc', 'iit bombay', 'iit delhi', 'iit kanpur', 'iit madras'],
    'TW': ['ntu', 'nthu', 'nctu'],
    'HK': ['hkust', 'hku', 'cuhk'],
    'AU': ['sydney', 'unsw', 'melbourne', 'monash', 'anu', 'uwa', 'uq', 'adelaide'],
    'CA': ['toronto', 'british columbia', 'mcmaster', 'waterloo', 'mcgill', 'quebec', 'calgary'],
    'BR': ['campinas', 'são paulo', 'usp', 'puc', 'coppe', 'ufmg'],
}

# Country name to code mapping
COUNTRY_NAME_TO_CODE = {
    'united states': 'US', 'usa': 'US', 'america': 'US',
    'china': 'CN', 'peoples republic of china': 'CN', 'prc': 'CN',
    'japan': 'JP', 'united kingdom': 'GB', 'uk': 'GB', 'britain': 'GB',
    'germany': 'DE', 'france': 'FR', 'canada': 'CA', 'australia': 'AU',
    'india': 'IN', 'singapore': 'SG', 'south korea': 'KR', 'korea': 'KR',
    'switzerland': 'CH', 'netherlands': 'NL', 'sweden': 'SE', 'norway': 'NO',
    'denmark': 'DK', 'finland': 'FI', 'belgium': 'BE', 'austria': 'AT',
    'israel': 'IL', 'italy': 'IT', 'spain': 'ES', 'portugal': 'PT',
    'greece': 'GR', 'hong kong': 'HK', 'taiwan': 'TW', 'thailand': 'TH',
    'brazil': 'BR', 'mexico': 'MX', 'argentina': 'AR', 'chile': 'CL',
    'ireland': 'IE', 'new zealand': 'NZ', 'south africa': 'ZA',
    'russia': 'RU', 'ukraine': 'UA', 'poland': 'PL', 'romania': 'RO',
    'czech republic': 'CZ', 'czechia': 'CZ', 'hungary': 'HU', 'turkey': 'TR',
}

# US state to code
US_STATES = ['california', 'massachusetts', 'texas', 'new york', 'illinois',
             'washington', 'colorado', 'utah', 'arizona', 'pennsylvania',
             'ohio', 'michigan', 'florida']

def detect_country_code(affiliation):
    """Detect country code from institution affiliation name."""
    if not affiliation or affiliation.lower() in ['unknown', '_unknown']:
        return None
    
    lower = affiliation.lower()
    
    # Check known institutions
    for country, institutions in KNOWN_INSTITUTIONS_BY_COUNTRY.items():
        for inst in institutions:
            if inst in lower:
                return country
    
    # Check country names
    for country_name, code in COUNTRY_NAME_TO_CODE.items():
        if country_name in lower:
            return code
    
    # Check US states
    for state in US_STATES:
        if state in lower:
            return 'US'
    
    # Check UK cities
    if any(city in lower for city in ['london', 'oxford', 'cambridge', 'edinburgh',
                                        'manchester', 'bristol', 'imperial']):
        return 'GB'
    
    # Check major cities
    city_to_country = {
        'paris': 'FR', 'munich': 'DE', 'berlin': 'DE', 'zurich': 'CH',
        'amsterdam': 'NL', 'stockholm': 'SE', 'oslo': 'NO', 'copenhagen': 'DK',
        'tokyo': 'JP', 'beijing': 'CN', 'shanghai': 'CN', 'hong kong': 'HK',
        'toronto': 'CA', 'melbourne': 'AU', 'sydney': 'AU',
        'delhi': 'IN', 'mumbai': 'IN', 'são paulo': 'BR', 'buenos aires': 'AR',
        'tel aviv': 'IL', 'prague': 'CZ', 'budapest': 'HU', 'warsaw': 'PL'
    }
    
    for city, code in city_to_country.items():
        if city in lower:
            return code
    
    return None

def calculate_repro_rate(artifacts, badges_reproducible):
    """Calculate reproducibility rate as percentage."""
    if artifacts == 0:
        return 0.0
    return (badges_reproducible / artifacts) * 100

def main():
    """Generate geographic statistics."""
    base_path = Path(__file__).parent
    website_path = base_path.parent / 'researchartifacts.github.io'
    data_dir = website_path / 'assets' / 'data'
    
    # Load institution rankings
    institution_path = data_dir / 'institution_rankings.json'
    if not institution_path.exists():
        print(f"✗ {institution_path} not found")
        return
    
    with open(institution_path, 'r', encoding='utf-8') as f:
        institutions = json.load(f)
    
    # Group by country and continent
    by_country = defaultdict(list)
    by_continent = defaultdict(list)
    
    for inst in institutions:
        aff = inst.get('affiliation', '')
        if not aff or aff.lower() in ['unknown', '_unknown']:
            continue
        
        country_code = detect_country_code(aff)
        if not country_code:
            continue
        
        continent = COUNTRY_TO_CONTINENT.get(country_code, 'Unknown')
        
        # Calculate rates
        repro_rate = calculate_repro_rate(
            inst.get('artifacts', 0),
            inst.get('badges_reproducible', 0)
        )
        
        functional_rate = calculate_repro_rate(
            inst.get('artifacts', 0),
            inst.get('badges_functional', 0)
        ) if inst.get('badges_functional') else 0
        
        artifact_rate = inst.get('artifact_rate', 0)  # % papers with artifacts
        
        inst_data = {
            'affiliation': aff,
            'country': country_code,
            'continent': continent,
            'num_authors': inst.get('num_authors', 0),
            'artifacts': inst.get('artifacts', 0),
            'total_papers': inst.get('total_papers', 0),
            'artifact_rate': artifact_rate,  # % of papers with artifacts
            'repro_rate': repro_rate,
            'functional_rate': functional_rate,
            'ae_memberships': inst.get('ae_memberships', 0),
            'combined_score': inst.get('combined_score', 0)
        }
        
        by_country[country_code].append(inst_data)
        by_continent[continent].append(inst_data)
    
    # Process statistics
    stats = {
        'generated': True,
        'by_country': {},
        'by_continent': {}
    }
    
    # Country statistics
    countries_sorted = sorted(by_country.keys())
    for country_code in countries_sorted:
        insts = by_country[country_code]
        continent = COUNTRY_TO_CONTINENT.get(country_code, 'Unknown')
        
        repro_rates = [i['repro_rate'] for i in insts if i['repro_rate'] > 0]
        artifact_rates = [i['artifact_rate'] for i in insts if i['artifact_rate'] > 0]
        functional_rates = [i['functional_rate'] for i in insts if i['functional_rate'] > 0]
        
        total_authors = sum(i['num_authors'] for i in insts)
        total_artifacts = sum(i['artifacts'] for i in insts)
        total_papers = sum(i['total_papers'] for i in insts)
        
        stats['by_country'][country_code] = {
            'continent': continent,
            'num_institutions': len(insts),
            'num_authors': total_authors,
            'num_artifacts': total_artifacts,
            'num_papers': total_papers,
            'papers_with_artifacts': int(total_papers * (sum(i['artifact_rate'] for i in insts) / len(insts)) / 100) if insts else 0,
            'reproducibility': {
                'median': round(median(repro_rates), 1) if repro_rates else 0,
                'mean': round(mean(repro_rates), 1) if repro_rates else 0,
                'min': round(min(repro_rates), 1) if repro_rates else 0,
                'max': round(max(repro_rates), 1) if repro_rates else 0,
                'institutions_in_top_50': sum(1 for i in insts if i['repro_rate'] >= 50),
            },
            'functionality': {
                'median': round(median(functional_rates), 1) if functional_rates else 0,
                'mean': round(mean(functional_rates), 1) if functional_rates else 0,
            },
            'artifact_availability': {
                'median': round(median(artifact_rates), 1) if artifact_rates else 0,
                'mean': round(mean(artifact_rates), 1) if artifact_rates else 0,
            }
        }
    
    # Continent statistics
    continents_sorted = sorted(by_continent.keys())
    for continent in continents_sorted:
        insts = by_continent[continent]
        
        repro_rates = [i['repro_rate'] for i in insts if i['repro_rate'] > 0]
        artifact_rates = [i['artifact_rate'] for i in insts if i['artifact_rate'] > 0]
        functional_rates = [i['functional_rate'] for i in insts if i['functional_rate'] > 0]
        
        total_authors = sum(i['num_authors'] for i in insts)
        total_artifacts = sum(i['artifacts'] for i in insts)
        total_papers = sum(i['total_papers'] for i in insts)
        
        unique_countries = len(set(i['country'] for i in insts))
        
        stats['by_continent'][continent] = {
            'num_countries': unique_countries,
            'num_institutions': len(insts),
            'num_authors': total_authors,
            'num_artifacts': total_artifacts,
            'num_papers': total_papers,
            'papers_with_artifacts': int(total_papers * (sum(i['artifact_rate'] for i in insts) / len(insts)) / 100) if insts else 0,
            'reproducibility': {
                'median': round(median(repro_rates), 1) if repro_rates else 0,
                'mean': round(mean(repro_rates), 1) if repro_rates else 0,
                'min': round(min(repro_rates), 1) if repro_rates else 0,
                'max': round(max(repro_rates), 1) if repro_rates else 0,
                'institutions_in_top_50': sum(1 for i in insts if i['repro_rate'] >= 50),
            },
            'functionality': {
                'median': round(median(functional_rates), 1) if functional_rates else 0,
                'mean': round(mean(functional_rates), 1) if functional_rates else 0,
            },
            'artifact_availability': {
                'median': round(median(artifact_rates), 1) if artifact_rates else 0,
                'mean': round(mean(artifact_rates), 1) if artifact_rates else 0,
            }
        }
    
    # Write output
    output_path = data_dir / 'geographic_statistics.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Generated {output_path}")
    print(f"  Continents: {len(stats['by_continent'])}")
    print(f"  Countries: {len(stats['by_country'])}")
    
    # Print highlights
    print("\n=== Geographic Statistics ===")
    print("\nTop 5 Countries by Artifacts:")
    top_countries = sorted(
        [(code, stats['by_country'][code]) for code in stats['by_country']],
        key=lambda x: x[1]['num_artifacts'],
        reverse=True
    )[:5]
    for code, data in top_countries:
        print(f"  {code}: {data['num_artifacts']} artifacts, "
              f"Repro: {data['reproducibility']['median']}%, "
              f"Authors: {data['num_authors']}")
    
    print("\nTop 5 Countries by Reproducibility:")
    repro_countries = sorted(
        [(code, stats['by_country'][code]) for code in stats['by_country']],
        key=lambda x: x[1]['reproducibility']['median'],
        reverse=True
    )[:5]
    for code, data in repro_countries:
        print(f"  {code}: {data['reproducibility']['median']}% (median), "
              f"{data['num_institutions']} institutions")
    
    print("\nBy Continent:")
    for continent in sorted(stats['by_continent'].keys()):
        data = stats['by_continent'][continent]
        print(f"  {continent}:")
        print(f"    Countries: {data['num_countries']}, Institutions: {data['num_institutions']}")
        print(f"    Artifacts: {data['num_artifacts']}, Papers: {data['num_papers']}")
        print(f"    Reproducibility (median): {data['reproducibility']['median']}%")

if __name__ == '__main__':
    main()
