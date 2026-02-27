import requests
import hashlib
import json
import os
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache')
CACHE_TTL = 86400 * 30           # 30 days – conference listings & raw file downloads
CACHE_TTL_URL = 86400 * 90       # 90 days – URL existence checks (positive)
CACHE_TTL_URL_NEG = 86400 * 7    # 7 days  – URL non-existence checks (re-check weekly)
CACHE_TTL_STATS = 86400 * 30     # 30 days – GitHub/Zenodo/Figshare stats

def _github_headers():
    """Return headers with GitHub token if available."""
    headers = {'Accept': 'application/vnd.github.v3+json'}
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    if token:
        headers['Authorization'] = f'token {token}'
    return headers

def _session_with_retries(retries=3, backoff=1.0, timeout=30):
    """Create a requests.Session with automatic retries and timeouts."""
    session = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=backoff,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    # Store default timeout on session for convenience
    session._default_timeout = timeout
    return session

# Module-level session reused across calls (connection pooling)
_session = _session_with_retries()

github_urls= {
    'sys': {
        'base_url': "https://github.com/sysartifacts/sysartifacts.github.io/blob/master/_conferences/",
        'raw_base_url': "https://raw.githubusercontent.com/sysartifacts/sysartifacts.github.io/master/_conferences/",
        'api_url': "https://api.github.com/repos/sysartifacts/sysartifacts.github.io/contents/_conferences/"
    },
    'sec': {
        'base_url': "https://github.com/secartifacts/secartifacts.github.io/blob/master/_conferences/",
        'raw_base_url': "https://raw.githubusercontent.com/secartifacts/secartifacts.github.io/master/_conferences/",
        'api_url': "https://api.github.com/repos/secartifacts/secartifacts.github.io/contents/_conferences/"
    }
}

def _cache_path(key, namespace='default'):
    """Return path to cache file for a given key and namespace."""
    ns_dir = os.path.join(CACHE_DIR, namespace)
    os.makedirs(ns_dir, exist_ok=True)
    hashed = hashlib.sha256(key.encode()).hexdigest()
    return os.path.join(ns_dir, hashed)

def _read_cache(key, ttl=CACHE_TTL, namespace='default'):
    """Return cached value if fresh, else None."""
    path = _cache_path(key, namespace)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r') as f:
            entry = json.load(f)
        if time.time() - entry['ts'] < ttl:
            return entry['body']
    except (json.JSONDecodeError, KeyError, OSError):
        pass
    return None

def _read_cache_entry(key, namespace='default'):
    """Return the full cache entry dict (body, ts, etag) regardless of TTL, or None."""
    path = _cache_path(key, namespace)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, KeyError, OSError):
        return None

def _write_cache(key, body, namespace='default', etag=None):
    """Write value to cache, optionally storing an ETag for conditional requests."""
    path = _cache_path(key, namespace)
    entry = {'ts': time.time(), 'body': body}
    if etag:
        entry['etag'] = etag
    with open(path, 'w') as f:
        json.dump(entry, f)

def _refresh_cache_ts(key, namespace='default'):
    """Touch the cache entry timestamp without changing its data (used after 304)."""
    path = _cache_path(key, namespace)
    try:
        with open(path, 'r') as f:
            entry = json.load(f)
        entry['ts'] = time.time()
        with open(path, 'w') as f:
            json.dump(entry, f)
    except (json.JSONDecodeError, KeyError, OSError):
        pass

def check_url_cached(url, ttl=CACHE_TTL_URL):
    """Check if a URL exists, with disk caching.

    Returns True/False.  Positive results are cached for ``ttl`` seconds;
    negative results are cached for CACHE_TTL_URL_NEG (shorter) so they
    are re-checked periodically without hammering every run.
    """
    cached = _read_cache(url, ttl=ttl, namespace='url_exists')
    if cached is True:
        return True  # positive hit – trust it
    # Check negative cache (shorter TTL)
    cached_neg = _read_cache(url, ttl=CACHE_TTL_URL_NEG, namespace='url_exists')
    if cached_neg is False:
        return False  # recently confirmed non-existent

    try:
        resp = _session.head(url, allow_redirects=True, timeout=10)
        if resp.status_code == 429:
            time.sleep(10)
            resp = _session.head(url, allow_redirects=True, timeout=10)
        exists = resp.status_code == 200
    except requests.RequestException as e:
        print(f"  Request error for {url}: {e}")
        exists = False

    _write_cache(url, exists, namespace='url_exists')
    return exists

def cached_github_stats(url, ttl=CACHE_TTL_STATS):
    """Fetch GitHub repo stats with caching, ETags, and rate-limit handling.

    Uses conditional requests (If-None-Match) so that 304 responses do NOT
    count against the GitHub API rate limit.  This effectively makes re-runs
    free for repos whose data hasn't changed.
    """
    cached = _read_cache(url, ttl=ttl, namespace='github_stats')
    if cached is not None:
        return cached  # dict or None — still fresh

    repo = url.split('github.com/')[1]
    for suffix in ('/tree/', '/blob/', '/pkgs/'):
        if suffix in repo:
            repo = repo.split(suffix)[0]
    repo = repo.rstrip('/').removesuffix('.git')

    headers = _github_headers()

    # Use stored ETag for conditional request (304 = free, no rate cost)
    entry = _read_cache_entry(url, namespace='github_stats')
    if entry and entry.get('etag'):
        headers['If-None-Match'] = entry['etag']

    resp = _session.get(f'https://api.github.com/repos/{repo}',
                        headers=headers, timeout=_session._default_timeout)
    if resp.status_code == 403 and 'rate limit' in resp.text.lower():
        reset_time = int(resp.headers.get('X-RateLimit-Reset', 0))
        wait = max(reset_time - int(time.time()), 0) + 5
        print(f"  Rate limited. Waiting {wait}s for reset...")
        time.sleep(wait)
        resp = _session.get(f'https://api.github.com/repos/{repo}',
                            headers=headers, timeout=_session._default_timeout)

    if resp.status_code == 304 and entry:
        # Data unchanged — refresh timestamp, return cached data (free!)
        _refresh_cache_ts(url, namespace='github_stats')
        return entry.get('body')
    elif resp.status_code == 200:
        d = resp.json()
        result = {
            'github_forks': d.get('forks_count', 0),
            'github_stars': d.get('stargazers_count', 0),
            'updated_at': d.get('updated_at', 'NA'),
            'created_at': d.get('created_at', 'NA'),
            'pushed_at': d.get('pushed_at', 'NA'),
            'name': d.get('full_name', 'NA'),
            'description': d.get('description', ''),
            'language': d.get('language', ''),
            'license': (d.get('license') or {}).get('spdx_id', ''),
            'topics': d.get('topics', []),
        }
        etag = resp.headers.get('ETag')
        _write_cache(url, result, namespace='github_stats', etag=etag)
        return result
    else:
        print(f'  Could not collect GitHub stats for {url} (HTTP {resp.status_code})')
        result = None
        _write_cache(url, result, namespace='github_stats')
        return result

def cached_zenodo_stats(url, ttl=CACHE_TTL_STATS):
    """Fetch Zenodo record stats with caching."""
    cached = _read_cache(url, ttl=ttl, namespace='zenodo_stats')
    if cached is not None:
        return cached

    if '/records/' in url:
        rec = url.split('/records/')[-1]
    elif 'zenodo.' in url:
        rec = url.split('zenodo.')[-1]
    else:
        print(f'  Could not parse Zenodo URL {url}')
        return None

    try:
        resp = _session.get(f'https://zenodo.org/api/records/{rec}',
                            timeout=_session._default_timeout)
        if resp.status_code == 200:
            record = resp.json()
            result = {
                'zenodo_views': record['stats']['unique_views'],
                'zenodo_downloads': record['stats']['unique_downloads'],
                'updated_at': record['updated'],
                'created_at': record['created'],
            }
        else:
            print(f'  Could not collect Zenodo stats for {url} (HTTP {resp.status_code})')
            result = None
    except requests.RequestException as e:
        print(f'  Zenodo request error for {url}: {e}')
        result = None

    _write_cache(url, result, namespace='zenodo_stats')
    return result

def cached_figshare_stats(url, ttl=CACHE_TTL_STATS):
    """Fetch Figshare article stats with caching."""
    cached = _read_cache(url, ttl=ttl, namespace='figshare_stats')
    if cached is not None:
        return cached

    clean = url
    if clean.endswith(('.v1', '.v2', '.v3', '.v4', '.v5', '.v6', '.v7', '.v8', '.v9')):
        clean = clean[:-3]
    article_id = clean.split('figshare.')[-1]

    views = downloads = -1
    updated = created = 'NA'
    try:
        r = _session.get(f'https://stats.figshare.com/total/views/article/{article_id}',
                         timeout=_session._default_timeout)
        if r.status_code == 200:
            views = r.json()['totals']
        r = _session.get(f'https://stats.figshare.com/total/downloads/article/{article_id}',
                         timeout=_session._default_timeout)
        if r.status_code == 200:
            downloads = r.json()['totals']
        r = _session.get(f'https://api.figshare.com/v2/articles/{article_id}',
                         timeout=_session._default_timeout)
        if r.status_code == 200:
            d = r.json()
            updated = d['modified_date']
            created = d['created_date']
    except requests.RequestException as e:
        print(f'  Figshare request error for {url}: {e}')

    result = {
        'figshare_views': views,
        'figshare_downloads': downloads,
        'updated_at': updated,
        'created_at': created,
    }
    _write_cache(url, result, namespace='figshare_stats')
    return result

def _cached_get(url):
    """requests.get with disk cache, ETag conditional requests, and GitHub auth.

    For GitHub API URLs, sends If-None-Match so that 304 responses are free
    (do not count against rate limits).
    """
    cached = _read_cache(url, ttl=CACHE_TTL, namespace='http_get')
    if cached is not None:
        return cached

    is_github_api = 'api.github.com' in url
    headers = _github_headers() if is_github_api else {}

    # Use stored ETag for conditional request if available
    entry = _read_cache_entry(url, namespace='http_get')
    if entry and entry.get('etag'):
        headers['If-None-Match'] = entry['etag']

    response = _session.get(url, headers=headers, allow_redirects=True,
                            timeout=_session._default_timeout)
    # Handle rate limiting with retry
    if response.status_code == 403 and 'rate limit' in response.text.lower():
        reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
        wait = max(reset_time - int(time.time()), 0) + 5
        print(f"  Rate limited. Waiting {wait}s for reset...")
        time.sleep(wait)
        response = _session.get(url, headers=headers, allow_redirects=True,
                                timeout=_session._default_timeout)

    if response.status_code == 304 and entry:
        # Data unchanged — refresh timestamp, return cached data (free!)
        _refresh_cache_ts(url, namespace='http_get')
        return entry.get('body')

    response.raise_for_status()
    body = response.text
    etag = response.headers.get('ETag')
    _write_cache(url, body, namespace='http_get', etag=etag)
    return body

def get_conferences_from_prefix(prefix):
    url = github_urls[prefix]['api_url']
    data = json.loads(_cached_get(url))
    return [item for item in data if item['type'] == 'dir']

def download_file(url):
    return _cached_get(url)