import requests
import re
import yaml
import argparse
from sys_sec_scrape import get_conferences_from_prefix, github_urls, download_file

def _parse_member_line(line):
    """Parse a single line from a committee markdown file into name + affiliation.

    Returns (name, affiliation) or (None, None) if the line should be skipped.
    """
    line = line.strip()
    if not line:
        return None, None
    # Skip markdown headings and separators
    if line.startswith('#') or line.startswith('---'):
        return None, None
    # Skip contact / email lines that are not actual names
    if 'reach the' in line.lower() or 'contact' in line.lower() and '@' in line:
        return None, None
    # Strip list markers
    start = 0
    if line.startswith('-') or line.startswith('*'):
        start = 1
        if len(line) > 1 and line[1] == ' ':
            start = 2
    line = line[start:].strip()
    if not line:
        return None, None
    # Strip markdown link syntax: [name](url) -> name
    link_match = re.match(r'\[([^\]]+)\]\([^)]*\)', line)
    if link_match:
        line = link_match.group(1) + line[link_match.end():]
    # Strip trailing <br> or <br/> tags
    line = re.sub(r'\s*<br\s*/?>$', '', line).strip()
    if not line:
        return None, None
    # Strip bold/italic markers
    line = line.strip('*_').strip()

    if '(' in line and ')' in line:
        name = line[:line.find('(')].strip()
        affiliation = line[line.find('(')+1:line.find(')')].strip()
    elif ',' in line:
        name = line.split(',')[0].strip()
        affiliation = line.split(',', 1)[1].strip()
    else:
        name = line
        affiliation = ''

    # Skip placeholder entries
    if name.lower() in ('you?', 'you', 'tba', 'tbd', ''):
        return None, None
    if len(name) <= 1:
        return None, None

    return name, affiliation


def get_committee_for_conference(conference, prefix):
    base_url = github_urls[prefix]['raw_base_url'] + conference
    # committee files are either named committee.md or organizers.md
    try:
        response = download_file(base_url + '/committee.md')
    except requests.exceptions.HTTPError as e:
        try:
            response = download_file(base_url + '/organizers.md')
        except requests.exceptions.HTTPError as e:
            print(f"couldn't get committee for {conference}")
            return None

    # --- Parse chairs and members separately ---
    # Look for chair sections before the AEC section
    committee = []
    lines = response.splitlines()

    # Identify section boundaries
    chair_lines = []
    member_lines = []
    current_section = None  # None, 'chair', 'member'

    for line in lines:
        stripped = line.strip().lower()
        # Detect chair heading
        if ('chair' in stripped and 'artifact' in stripped) or \
           (stripped.startswith('**chair') and stripped.endswith('**:')) or \
           re.match(r'^#{1,4}\s*.*chair', stripped) or \
           (stripped.startswith('**chair')):
            current_section = 'chair'
            continue
        # Detect member/committee heading
        if re.match(r'^#{1,4}\s*.*artifact\s*evaluation\s*committee', stripped) or \
           re.match(r'^#{1,4}\s*.*\bmembers?\b', stripped) or \
           (stripped.startswith('**member') and stripped.endswith('**:')):
            current_section = 'member'
            continue
        if current_section == 'chair':
            chair_lines.append(line)
        elif current_section == 'member':
            member_lines.append(line)

    # If no sections detected, fall back to original split approach
    if not chair_lines and not member_lines:
        committees_text = response.split('Artifact Evaluation Committee')
        aec = committees_text[len(committees_text)-1].strip()
        for line in aec.splitlines():
            name, affiliation = _parse_member_line(line)
            if name:
                committee.append({'name': name, 'affiliation': affiliation, 'role': 'member'})
        return committee

    # Parse chairs
    for line in chair_lines:
        name, affiliation = _parse_member_line(line)
        if name:
            committee.append({'name': name, 'affiliation': affiliation, 'role': 'chair'})

    # Parse members
    for line in member_lines:
        name, affiliation = _parse_member_line(line)
        if name:
            committee.append({'name': name, 'affiliation': affiliation, 'role': 'member'})

    # If only chairs found (no member section), also parse the AEC section
    if not member_lines:
        committees_text = response.split('Artifact Evaluation Committee')
        if len(committees_text) > 1:
            aec = committees_text[-1].strip()
            for line in aec.splitlines():
                name, affiliation = _parse_member_line(line)
                if name:
                    # Don't add duplicates (chairs already added)
                    if not any(m['name'] == name for m in committee):
                        committee.append({'name': name, 'affiliation': affiliation, 'role': 'member'})

    return committee

def get_committees(conference_regex, prefix):
    results = {}
    # get conference name from prefix
    conferences = get_conferences_from_prefix(prefix)
    if conferences is None:
        print(f"Invalid prefix: {prefix}")
        return results
    # get the base url for the conference
    for conf in conferences:
        if re.search(conference_regex, conf['name']):
            name = conf['name']
            if name in results:
                continue
            # add year
            committee = get_committee_for_conference(name, prefix)
            if committee:
                results[name] = committee

    return results

def main():

    parser = argparse.ArgumentParser(description='Scraping results of sys/secartifacts.github.io from conferences.')
    parser.add_argument('--conf_regex', type=str, default='.20[1|2][0-9]', help='Regular expression for conference name and or years')
    parser.add_argument('--prefix', type=str, default='sys', help='Prefix of artifacts website like sys for sysartifacts or sec for secartifacts')
    parser.add_argument('--print', action='store_true', help='Print committees')

    args = parser.parse_args()

    results = get_committees(args.conf_regex, args.prefix)

    for year in results.keys():
        print(f"{year}: {len(results[year])}")

    if args.print:
        for year in results.keys():
            print(results[year])

if __name__ == "__main__":
    main()