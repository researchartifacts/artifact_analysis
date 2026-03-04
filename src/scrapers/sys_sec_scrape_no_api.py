"""
Scraper for sysartifacts and secartifacts that works without GitHub API
Uses direct website scraping and raw GitHub URLs
"""
import requests
from bs4 import BeautifulSoup
import re

github_urls = {
    'sys': {
        'website': "https://sysartifacts.github.io/",
        'raw_base_url': "https://raw.githubusercontent.com/sysartifacts/sysartifacts.github.io/master/"
    },
    'sec': {
        'website': "https://secartifacts.github.io/",
        'raw_base_url': "https://raw.githubusercontent.com/secartifacts/secartifacts.github.io/master/"
    }
}

def get_conferences_from_prefix(prefix):
    """
    Scrape conference list from the website instead of using GitHub API
    Returns a list of conference names (directories)
    """
    url = github_urls[prefix]['website']
    print(f"Scraping {url}...")
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find all conference links (format: /conference or /conference2024)
    conferences = set()
    for link in soup.find_all('a', href=True):
        href = link['href']
        # Match conference pages like /osdi2024, /sosp2023, etc.
        if re.match(r'^/[a-z]+\d{4}$', href):
            conf_name = href[1:]  # Remove leading /
            conferences.add(conf_name)
    
    # Convert to format similar to API response
    conf_list = [{'name': conf, 'type': 'dir'} for conf in sorted(conferences)]
    print(f"Found {len(conf_list)} conferences")
    return conf_list

def download_file(url):
    """Download a file from raw GitHub URL"""
    print(f"Downloading {url}...")
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.text

def get_conference_artifacts(prefix, conference_name):
    """
    Get artifacts for a specific conference by scraping the conference page
    """
    url = f"{github_urls[prefix]['website']}{conference_name}"
    print(f"Scraping artifacts from {url}...")
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except:
        print(f"Could not access {url}")
        return []
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Try to find artifact entries
    # The structure varies, but typically artifacts are in sections or divs
    artifacts = []
    
    # Look for artifact cards/entries
    # This is a simplified extraction - may need adjustment based on actual HTML structure
    for section in soup.find_all(['section', 'div', 'article']):
        # Look for badges
        badges = []
        if 'Available' in str(section) or 'available' in str(section):
            badges.append('Available')
        if 'Functional' in str(section) or 'functional' in str(section):
            badges.append('Functional')
        if 'Reproducible' in str(section) or 'reproduced' in str(section).lower():
            badges.append('Reproducible')
        if 'Replicated' in str(section) or 'replicated' in str(section).lower():
            badges.append('Replicated')
        if 'Results Validated' in str(section) or 'validated' in str(section).lower():
            badges.append('Results Validated')
        
        if badges:
            # Try to extract title
            title = "Unknown"
            for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'strong', 'b']:
                title_elem = section.find(tag)
                if title_elem:
                    title = title_elem.get_text().strip()
                    break
            
            artifacts.append({
                'title': title,
                'badges': badges,
                'conference': conference_name
            })
    
    return artifacts
