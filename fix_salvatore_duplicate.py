#!/usr/bin/env python3
"""Fix Salvatore Signorello duplicate in ae_members.json"""

import json
import sys

def fix_salvatore_duplicate(input_file, output_file):
    """Merge the two Salvatore Signorello entries"""
    with open(input_file, 'r') as f:
        data = json.load(f)
    
    # Find both entries
    signorello_entries = []
    other_entries = []
    
    for entry in data:
        if 'Salvatore Signorello' in entry.get('name', ''):
            signorello_entries.append(entry)
        else:
            other_entries.append(entry)
    
    if len(signorello_entries) != 2:
        print(f"Expected 2 Salvatore Signorello entries, found {len(signorello_entries)}")
        return False
    
    # Merge: keep the first (more complete) entry and add the missing membership
    main_entry = None
    secondary_entry = None
    
    for entry in signorello_entries:
        if entry.get('total_memberships', 0) > 1:
            main_entry = entry
        else:
            secondary_entry = entry
    
    if not main_entry or not secondary_entry:
        print("Could not identify main and secondary entries")
        return False
    
    print(f"Main entry: {main_entry['name']} - {main_entry['total_memberships']} memberships")
    print(f"  Conferences: {main_entry['conferences']}")
    print(f"  Years: {main_entry['years']}")
    print(f"Secondary entry: {secondary_entry['name']} - {secondary_entry['total_memberships']} memberships")
    print(f"  Conferences: {secondary_entry['conferences']}")
    print(f"  Years: {secondary_entry['years']}")
    
    # Merge conferences
    for conf in secondary_entry.get('conferences', []):
        if conf not in main_entry['conferences']:
            main_entry['conferences'].append(conf)
    main_entry['conferences'].sort()
    
    # Merge years
    for year, count in secondary_entry.get('years', {}).items():
        main_entry['years'][year] = main_entry['years'].get(year, 0) + count
    
    # Update totals
    main_entry['total_memberships'] += secondary_entry['total_memberships']
    main_entry['first_year'] = min(main_entry['first_year'], secondary_entry['first_year'])
    main_entry['last_year'] = max(main_entry['last_year'], secondary_entry['last_year'])
    
    # Add main entry back to data
    other_entries.append(main_entry)
    
    print(f"\nMerged entry: {main_entry['name']} - {main_entry['total_memberships']} memberships")
    print(f"  Conferences: {main_entry['conferences']}")
    print(f"  Years: {main_entry['years']}")
    
    # Write output
    with open(output_file, 'w') as f:
        json.dump(other_entries, f, indent=2)
    
    print(f"\nWrote {len(other_entries)} entries to {output_file}")
    return True

if __name__ == '__main__':
    input_file = '../researchartifacts.github.io/assets/data/ae_members.json'
    output_file = '../researchartifacts.github.io/assets/data/ae_members.json'
    
    if fix_salvatore_duplicate(input_file, output_file):
        print("Successfully fixed duplicate!")
        sys.exit(0)
    else:
        print("Failed to fix duplicate")
        sys.exit(1)
