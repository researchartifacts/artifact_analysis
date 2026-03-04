#!/usr/bin/env python3
"""
Scrape AE committee data from alternative sources when sysartifacts/secartifacts
GitHub repos don't have the information.

Supported sources:
- USENIX website (FAST, OSDI, ATC, USENIX Security, WOOT)
- CHES website (ches.iacr.org)
- PETS website (petsymposium.org)
"""

import re
import sys
import requests
from bs4 import BeautifulSoup

# ── USENIX conference URL patterns ──────────────────────────────────────────

# Maps our internal conference name to the USENIX URL slug.
# Key: lowercase conference name as used in sysartifacts (e.g. "fast", "osdi")
# Value: USENIX slug prefix (year suffix is appended as 2-digit)
USENIX_CONF_SLUGS = {
    'fast': 'fast',
    'osdi': 'osdi',
    'atc': 'atc',
    'usenixsec': 'usenixsecurity',
    'woot': 'woot',
}

# Known years where USENIX call-for-artifacts pages exist
USENIX_KNOWN_YEARS = {
    'fast': range(2024, 2026),       # 2024, 2025
    'osdi': range(2020, 2026),       # 2020-2025  (some may 404)
    'atc': range(2020, 2026),        # 2020-2025  (some may 404)
    'usenixsec': range(2020, 2026),  # 2020-2025
    'woot': range(2024, 2026),       # 2024 (2025 may exist)
}

BASE_USENIX = "https://www.usenix.org"


def _get_session():
    """Return a requests session with a polite user-agent."""
    s = requests.Session()
    s.headers.update({
        'User-Agent': 'ResearchArtifacts/1.0 (artifact statistics collection)'
    })
    return s


def _parse_usenix_views_rows(heading):
    """Parse committee from newer USENIX format using views-row divs.

    Format: <div class="views-row ...">
              <div class="views-field views-field-field-speakers-institution">
                <div class="field-content">Name, <em>Affiliation</em></div>
              </div>
            </div>
    """
    members = []
    for sib in heading.next_siblings:
        if not hasattr(sib, 'name'):
            continue
        # Stop at next heading
        if sib.name in ('h2', 'h3', 'h4'):
            break
        if sib.name == 'div' and 'views-row' in ' '.join(sib.get('class', [])):
            # Find field-content div
            fc = sib.find('div', class_='field-content')
            if fc:
                # Parse "Name, <em>Affiliation</em>"
                em = fc.find('em')
                affiliation = em.get_text().strip() if em else ''
                # Name is the text before the <em>
                name_parts = []
                for child in fc.children:
                    if hasattr(child, 'name') and child.name == 'em':
                        break
                    text = str(child) if not hasattr(child, 'name') else child.get_text()
                    name_parts.append(text)
                name = ''.join(name_parts).strip().rstrip(',').strip()
                name = re.sub(r'\s+', ' ', name).strip('*_').strip()
                affiliation = re.sub(r'\s+', ' ', affiliation).strip('*_').strip()
                if name and len(name) > 1:
                    members.append({'name': name, 'affiliation': affiliation, 'role': 'member'})
    return members


def _parse_usenix_committee_html(soup):
    """Parse committee members from a USENIX call-for-artifacts page.

    The USENIX format uses:
      <h2|h3>Artifact Evaluation Committee</h2|h3>
      <p style="line-height: 24px;">
        Name, <em>Affiliation</em><br/>
        Name, <em>Affiliation</em><br/>
        ...
      </p>

    Returns list of {name, affiliation} dicts.
    """
    members = []

    # Find headings containing "Artifact Evaluation Committee"
    # We want the one that is exactly "Artifact Evaluation Committee"
    # (not "Co-Chairs", not "Membership")
    target_heading = None
    for h in soup.find_all(['h2', 'h3', 'h4']):
        txt = h.get_text().strip().lower()
        if txt == 'artifact evaluation committee':
            target_heading = h
            # Don't break — prefer the LAST match (the sub-heading for members)
        elif txt == 'artifact evaluation committee (aec)':
            target_heading = h

    if target_heading is None:
        return members

    # Try two formats:
    # Format A (older): <p> with <br/> separated entries
    # Format B (newer): <div class="views-row"> divs with nested field-content

    next_sib = target_heading.find_next_sibling()

    # Check if Format B (views-row divs)
    if next_sib and hasattr(next_sib, 'name') and next_sib.name == 'div' and \
       'views-row' in ' '.join(next_sib.get('class', [])):
        return _parse_usenix_views_rows(target_heading)

    # Format A: find the next <p> sibling
    p_tag = target_heading.find_next_sibling('p')
    if p_tag is None:
        for sib in target_heading.next_siblings:
            if hasattr(sib, 'name') and sib.name == 'p':
                p_tag = sib
                break
            elif hasattr(sib, 'name') and sib.name in ('h2', 'h3', 'h4'):
                break

    if p_tag is None:
        return members

    # Parse the <p> content: split by <br> tags
    lines = []
    current_parts = []

    for child in p_tag.children:
        if hasattr(child, 'name') and child.name == 'br':
            if current_parts:
                lines.append(''.join(current_parts).strip())
                current_parts = []
        elif hasattr(child, 'name') and child.name == 'em':
            current_parts.append(child.get_text())
        elif hasattr(child, 'name') and child.name == 'a':
            current_parts.append(child.get_text())
        else:
            text = str(child) if not hasattr(child, 'name') else child.get_text()
            current_parts.append(text)

    if current_parts:
        last = ''.join(current_parts).strip()
        if last:
            lines.append(last)

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Skip non-member lines
        if line.startswith('http') or '@' in line or line.startswith('['):
            continue

        # Parse "Name, Affiliation"
        # The affiliation was in <em> tags, so it's already extracted as plain text
        if ',' in line:
            parts = line.split(',', 1)
            name = parts[0].strip()
            affiliation = parts[1].strip()
        else:
            name = line
            affiliation = ''

        # Clean up
        name = re.sub(r'\s+', ' ', name).strip().strip('*_').strip()
        affiliation = re.sub(r'\s+', ' ', affiliation).strip().strip('*_').strip()

        if name and len(name) > 1:
            members.append({'name': name, 'affiliation': affiliation, 'role': 'member'})

    return members


def _parse_usenix_cochairs_html(soup):
    """Parse co-chairs from a USENIX call-for-artifacts page.

    Returns list of {name, affiliation} dicts.
    """
    members = []

    for h in soup.find_all(['h2', 'h3', 'h4']):
        txt = h.get_text().strip().lower()
        if 'co-chair' in txt and 'artifact' in txt:
            # Check for views-row format first
            next_sib = h.find_next_sibling()
            if next_sib and hasattr(next_sib, 'name') and next_sib.name == 'div' and \
               'views-row' in ' '.join(next_sib.get('class', [])):
                members.extend(_parse_usenix_views_rows(h))
                break
            p_tag = h.find_next_sibling('p')
            if p_tag:
                # Parse same format
                lines = []
                current_parts = []
                for child in p_tag.children:
                    if hasattr(child, 'name') and child.name == 'br':
                        if current_parts:
                            lines.append(''.join(current_parts).strip())
                            current_parts = []
                    elif hasattr(child, 'name') and child.name == 'em':
                        current_parts.append(child.get_text())
                    else:
                        text = str(child) if not hasattr(child, 'name') else child.get_text()
                        current_parts.append(text)
                if current_parts:
                    last = ''.join(current_parts).strip()
                    if last:
                        lines.append(last)
                for line in lines:
                    line = line.strip()
                    if not line or '@' in line:
                        continue
                    if ',' in line:
                        parts = line.split(',', 1)
                        name = parts[0].strip()
                        affiliation = parts[1].strip()
                    else:
                        name = line
                        affiliation = ''
                    name = re.sub(r'\s+', ' ', name).strip().strip('*_').strip()
                    affiliation = re.sub(r'\s+', ' ', affiliation).strip().strip('*_').strip()
                    if name and len(name) > 1:
                        members.append({'name': name, 'affiliation': affiliation, 'role': 'chair'})
            break  # only process first co-chair heading

    return members


def scrape_usenix_committee(conference, year, session=None):
    """Scrape AE committee from a USENIX conference call-for-artifacts page.

    Parameters
    ----------
    conference : str
        Conference name (e.g. 'fast', 'osdi', 'usenixsec', 'woot')
    year : int
        4-digit year
    session : requests.Session, optional

    Returns
    -------
    list of {name, affiliation} dicts, or None if page not found
    """
    slug = USENIX_CONF_SLUGS.get(conference.lower())
    if slug is None:
        return None

    yy = str(year)[2:]  # e.g. 2024 -> "24"
    url = f"{BASE_USENIX}/conference/{slug}{yy}/call-for-artifacts"

    sess = session or _get_session()
    try:
        resp = sess.get(url, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  Warning: Failed to fetch {url}: {e}", file=sys.stderr)
        return None

    soup = BeautifulSoup(resp.text, 'html.parser')

    # Parse co-chairs and regular committee members
    chairs = _parse_usenix_cochairs_html(soup)
    members = _parse_usenix_committee_html(soup)

    # Mark roles
    for m in chairs:
        m['role'] = 'chair'
    for m in members:
        m['role'] = 'member'

    # Combine (chairs + members, dedup by name)
    all_members = chairs + members
    seen = set()
    deduped = []
    for m in all_members:
        if m['name'].lower() not in seen:
            seen.add(m['name'].lower())
            deduped.append(m)

    if deduped:
        print(f"  USENIX: Found {len(deduped)} members for {conference}{year}", file=sys.stderr)
    return deduped if deduped else None


# ── CHES scraper ─────────────────────────────────────────────────────────────

# CHES publishes committee data as JSON (loaded dynamically on the HTML page)
# for 2023+. Chair info is only available in the static HTML page.
# CHES 2022 has no JSON API; members must be scraped from HTML.
CHES_KNOWN_YEARS = range(2022, 2027)


def _scrape_ches_chairs_html(soup):
    """Parse chair(s) from a CHES artifacts HTML page.

    Looks for an <h3> heading containing "Artifact Review Chair" or
    "Artifact Evaluation Co-Chairs", then extracts <h4>/<p> pairs from the
    following ``<div class="row">`` element.

    Returns list of {name, affiliation, role:'chair'} dicts.
    """
    chairs = []
    for h3 in soup.find_all('h3'):
        txt = h3.get_text().strip().lower()
        if 'chair' in txt and 'artifact' in txt:
            row_div = h3.find_next_sibling('div', class_='row')
            if row_div:
                for aside in row_div.find_all('aside'):
                    h4 = aside.find('h4')
                    p = aside.find('p')
                    if h4:
                        name = re.sub(r'\s+', ' ', h4.get_text()).strip()
                        affiliation = re.sub(r'\s+', ' ', p.get_text()).strip() if p else ''
                        if name and len(name) > 1:
                            chairs.append({
                                'name': name,
                                'affiliation': affiliation,
                                'role': 'chair',
                            })
            break  # only process the first matching heading
    return chairs


def _scrape_ches_members_html(soup):
    """Parse committee members from the static HTML list (CHES 2022 format).

    Format::

        <h3>Artifact Review Committee Members</h3>
        <ul>
          <li>Name (Affiliation, Country)</li>
          ...
        </ul>

    Returns list of {name, affiliation, role:'member'} dicts.
    """
    members = []
    for h3 in soup.find_all('h3'):
        txt = h3.get_text().strip().lower()
        if 'committee member' in txt and 'artifact' in txt:
            ul = h3.find_next_sibling('ul')
            if ul:
                for li in ul.find_all('li'):
                    text = li.get_text().strip()
                    # Parse "Name (Affiliation, Country)"
                    m = re.match(r'^(.+?)\s*\((.+)\)\s*$', text)
                    if m:
                        name = re.sub(r'\s+', ' ', m.group(1)).strip()
                        affiliation = re.sub(r'\s+', ' ', m.group(2)).strip()
                    else:
                        name = re.sub(r'\s+', ' ', text).strip()
                        affiliation = ''
                    if name and len(name) > 1:
                        members.append({
                            'name': name,
                            'affiliation': affiliation,
                            'role': 'member',
                        })
            break
    return members


def scrape_ches_committee(year, session=None):
    """Scrape AE committee from the CHES website.

    Members are fetched from the JSON API
    (``ches.iacr.org/{year}/json/artifact.json``).  If the JSON endpoint is
    unavailable (e.g. CHES 2022), members are parsed from the static HTML.
    Chairs are always scraped from the HTML page
    (``ches.iacr.org/{year}/artifacts.php``) because the JSON data does not
    include chair information.

    Returns list of {name, affiliation, role} dicts, or None if not found.
    """
    sess = session or _get_session()
    members = []

    # 1. Try JSON API for members
    json_url = f"https://ches.iacr.org/{year}/json/artifact.json"
    try:
        resp = sess.get(json_url, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            for entry in data.get('committee', []):
                name = re.sub(r'\s+', ' ', entry.get('name', '')).strip()
                affiliation = re.sub(r'\s+', ' ', entry.get('affiliation', '')).strip()
                if name and len(name) > 1:
                    members.append({'name': name, 'affiliation': affiliation, 'role': 'member'})
    except (requests.RequestException, ValueError, KeyError):
        pass

    # 2. Fetch HTML page for chairs (and fallback members if JSON failed)
    html_url = f"https://ches.iacr.org/{year}/artifacts.php"
    try:
        resp = sess.get(html_url, timeout=30)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')

            # Parse chairs from HTML
            chairs = _scrape_ches_chairs_html(soup)

            # If JSON didn't return members, try HTML fallback (CHES 2022)
            if not members:
                members = _scrape_ches_members_html(soup)

            # Combine: chairs first, then members (dedup by name)
            all_members = chairs + members
            seen = set()
            deduped = []
            for m in all_members:
                key = m['name'].lower()
                if key not in seen:
                    seen.add(key)
                    deduped.append(m)

            if deduped:
                chair_count = sum(1 for m in deduped if m['role'] == 'chair')
                member_count = len(deduped) - chair_count
                print(f"  CHES: Found {member_count} members + {chair_count} chair(s) for ches{year}",
                      file=sys.stderr)
            return deduped if deduped else None
    except requests.RequestException as e:
        print(f"  Warning: Failed to fetch {html_url}: {e}", file=sys.stderr)

    # If only JSON members were found (HTML failed), return those
    if members:
        print(f"  CHES: Found {len(members)} members for ches{year} (JSON only)", file=sys.stderr)
        return members

    return None


# ── PETS scraper ─────────────────────────────────────────────────────────────

# PETS publishes ARC on cfp pages for each year.
# Available for 2020-2026.
PETS_KNOWN_YEARS = range(2020, 2027)


def scrape_pets_committee(year, session=None):
    """Scrape artifact review committee from PETS/PoPETs website.

    PETS publishes ARC on: petsymposium.org/cfp{YY}.php
    Format: <dt><font><b>Artifact Review Committee:</b></font></dt>
            <dd>Name, <i>Affiliation</i></dd>
            <dd>Name, <i>Affiliation</i></dd>
            ...

    Returns list of {name, affiliation} dicts, or None if not found.
    """
    yy = str(year)[2:]
    url = f"https://petsymposium.org/cfp{yy}.php"
    sess = session or _get_session()

    try:
        resp = sess.get(url, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  Warning: Failed to fetch {url}: {e}", file=sys.stderr)
        return None

    soup = BeautifulSoup(resp.text, 'html.parser')
    members = []

    # Find the <dt> element containing "Artifact Review Committee"
    arc_dt = None
    for dt in soup.find_all('dt'):
        txt = dt.get_text().lower()
        if 'artifact' in txt and 'committee' in txt:
            arc_dt = dt
            break

    if arc_dt is None:
        return None

    # Collect all <dd> siblings following the <dt> until the next <dt>
    for sib in arc_dt.next_siblings:
        if not hasattr(sib, 'name'):
            continue
        if sib.name == 'dt':
            break  # reached the next definition term
        if sib.name == 'dd':
            text = sib.get_text().strip()
            if not text or len(text) < 3:
                continue
            # Parse "Name, Affiliation"
            if ',' in text:
                parts = text.split(',', 1)
                name = parts[0].strip()
                affiliation = parts[1].strip()
            else:
                name = text
                affiliation = ''
            name = re.sub(r'\s+', ' ', name).strip().strip('*_').strip()
            affiliation = re.sub(r'\s+', ' ', affiliation).strip().strip('*_').strip()
            if name and len(name) > 2:
                members.append({'name': name, 'affiliation': affiliation, 'role': 'member'})

    if members:
        print(f"  PETS: Found {len(members)} members for pets{year}", file=sys.stderr)
    return members if members else None


# ── Public API ───────────────────────────────────────────────────────────────

def get_alternative_committees(conferences_needed):
    """Fetch committees from alternative sources for conferences not in sysartifacts/secartifacts.

    Parameters
    ----------
    conferences_needed : dict
        {conf_year_str: 'systems'|'security'} — conferences that need data.
        e.g. {'fast2024': 'systems', 'usenixsec2022': 'security'}

    Returns
    -------
    dict of {conf_year_str: [{name, affiliation}, ...]}
    """
    results = {}
    sess = _get_session()

    for conf_year_str, area in conferences_needed.items():
        m = re.match(r'^([a-zA-Z]+)(\d{4})$', conf_year_str)
        if not m:
            continue
        conf = m.group(1).lower()
        year = int(m.group(2))

        committee = None

        # Try USENIX website
        if conf in USENIX_CONF_SLUGS:
            committee = scrape_usenix_committee(conf, year, session=sess)

        # Try CHES website
        elif conf == 'ches':
            committee = scrape_ches_committee(year, session=sess)

        # Try PETS website
        elif conf == 'pets':
            committee = scrape_pets_committee(year, session=sess)

        if committee and len(committee) > 0:
            results[conf_year_str] = committee

    return results


def get_all_usenix_committees(conf_regex=None):
    """Scrape all available USENIX conference committees.

    Parameters
    ----------
    conf_regex : str, optional
        Regex to filter conference/year strings (e.g. '.20[2][0-5]')

    Returns
    -------
    dict of {conf_year_str: [{name, affiliation}, ...]}
    """
    results = {}
    sess = _get_session()

    for conf, years in USENIX_KNOWN_YEARS.items():
        for year in years:
            conf_year = f"{conf}{year}"
            if conf_regex and not re.search(conf_regex, conf_year):
                continue
            committee = scrape_usenix_committee(conf, year, session=sess)
            if committee:
                results[conf_year] = committee

    return results


# ── CLI for testing ──────────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Scrape AE committees from alternative sources')
    parser.add_argument('--conference', type=str, help='Conference name (fast, osdi, usenixsec, woot, ches, pets)')
    parser.add_argument('--year', type=int, help='Year (e.g. 2024)')
    parser.add_argument('--all-usenix', action='store_true', help='Scrape all known USENIX committees')
    parser.add_argument('--all-ches', action='store_true', help='Scrape all CHES years 2021-2025')
    parser.add_argument('--all-pets', action='store_true', help='Scrape all PETS years 2020-2025')
    args = parser.parse_args()

    if args.all_usenix:
        results = get_all_usenix_committees()
        for cy, members in sorted(results.items()):
            print(f"{cy}: {len(members)} members")
    elif args.all_ches:
        sess = _get_session()
        for y in CHES_KNOWN_YEARS:
            committee = scrape_ches_committee(y, session=sess)
            if committee:
                print(f"ches{y}: {len(committee)} members")
            else:
                print(f"ches{y}: not found")
    elif args.all_pets:
        sess = _get_session()
        for y in PETS_KNOWN_YEARS:
            committee = scrape_pets_committee(y, session=sess)
            if committee:
                print(f"pets{y}: {len(committee)} members")
            else:
                print(f"pets{y}: not found")
    elif args.conference and args.year:
        conf = args.conference.lower()
        if conf in USENIX_CONF_SLUGS:
            result = scrape_usenix_committee(conf, args.year)
        elif conf == 'ches':
            result = scrape_ches_committee(args.year)
        elif conf == 'pets':
            result = scrape_pets_committee(args.year)
        else:
            print(f"Unknown conference: {conf}")
            sys.exit(1)

        if result:
            print(f"Found {len(result)} members:")
            for m in result:
                print(f"  {m['name']} — {m['affiliation']}")
        else:
            print("No committee data found.")
    else:
        parser.print_help()
