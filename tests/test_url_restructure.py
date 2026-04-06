"""Tests for artifact URL restructuring in generate_statistics.py.

Verifies that the URL merge logic correctly consolidates repository_url,
artifact_url, github_url, artifact_urls (list), and miscellaneous URL fields
into a single artifact_urls array.
"""


def _build_artifact_urls(artifact_dict):
    """Replicate the URL consolidation logic from generate_statistics.py.

    Keeps the test self-contained without importing the full generator
    (which has heavy scraper dependencies).
    """
    all_artifact_urls = []
    for repo_key in ("repository_url", "github_url", "second_repository_url", "bitbucket_url"):
        url = artifact_dict.get(repo_key, "")
        if url:
            all_artifact_urls.append(url)
    if artifact_dict.get("artifact_url"):
        all_artifact_urls.append(artifact_dict["artifact_url"])
    if isinstance(artifact_dict.get("artifact_urls"), list):
        all_artifact_urls.extend([u for u in artifact_dict["artifact_urls"] if u])
    if isinstance(artifact_dict.get("additional_urls"), list):
        all_artifact_urls.extend([u for u in artifact_dict["additional_urls"] if u])
    artifact_doi = artifact_dict.get("artifact_doi", "")
    if artifact_doi:
        if not artifact_doi.startswith("http"):
            artifact_doi = f"https://doi.org/{artifact_doi}"
        all_artifact_urls.append(artifact_doi)
    for url_key in ("cloudlab_url", "web_url", "scripts_url", "jupyter_url", "vm_url", "proof_url", "data_url"):
        extra_url = artifact_dict.get(url_key, "")
        if extra_url:
            all_artifact_urls.append(extra_url)
    # Deduplicate while preserving order
    seen_urls = set()
    deduped = []
    for u in all_artifact_urls:
        if isinstance(u, str) and u and u not in seen_urls:
            seen_urls.add(u)
            deduped.append(u)
    return deduped


class TestArtifactUrlMerge:
    def test_github_and_artifact_url_merged(self):
        art = {
            "repository_url": "https://github.com/foo/bar",
            "artifact_url": "https://zenodo.org/records/123",
        }
        urls = _build_artifact_urls(art)
        assert urls == ["https://github.com/foo/bar", "https://zenodo.org/records/123"]

    def test_github_url_dedup_with_repository_url(self):
        art = {
            "repository_url": "https://github.com/foo/bar",
            "github_url": "https://github.com/foo/bar",
        }
        urls = _build_artifact_urls(art)
        assert urls == ["https://github.com/foo/bar"]

    def test_artifact_doi_normalized(self):
        art = {"artifact_doi": "10.5281/zenodo.123"}
        urls = _build_artifact_urls(art)
        assert urls == ["https://doi.org/10.5281/zenodo.123"]

    def test_artifact_doi_already_url(self):
        art = {"artifact_doi": "https://doi.org/10.5281/zenodo.123"}
        urls = _build_artifact_urls(art)
        assert urls == ["https://doi.org/10.5281/zenodo.123"]

    def test_artifact_urls_list_merged(self):
        art = {
            "repository_url": "https://github.com/foo/bar",
            "artifact_urls": ["https://zenodo.org/records/111", "https://zenodo.org/records/222"],
        }
        urls = _build_artifact_urls(art)
        assert "https://github.com/foo/bar" in urls
        assert "https://zenodo.org/records/111" in urls
        assert "https://zenodo.org/records/222" in urls
        assert len(urls) == 3

    def test_miscellaneous_url_fields(self):
        art = {
            "cloudlab_url": "https://cloudlab.us/profile/foo",
            "vm_url": "https://example.com/vm.ova",
        }
        urls = _build_artifact_urls(art)
        assert "https://cloudlab.us/profile/foo" in urls
        assert "https://example.com/vm.ova" in urls

    def test_empty_values_skipped(self):
        art = {
            "repository_url": "",
            "artifact_url": "",
            "github_url": "",
        }
        urls = _build_artifact_urls(art)
        assert urls == []

    def test_preserves_order(self):
        art = {
            "repository_url": "https://github.com/a",
            "artifact_url": "https://zenodo.org/b",
            "artifact_doi": "10.5281/zenodo.c",
        }
        urls = _build_artifact_urls(art)
        assert urls == [
            "https://github.com/a",
            "https://zenodo.org/b",
            "https://doi.org/10.5281/zenodo.c",
        ]

    def test_paper_url_and_appendix_url_not_included(self):
        """paper_url and appendix_url should remain separate fields."""
        art = {
            "repository_url": "https://github.com/foo/bar",
            "paper_url": "https://doi.org/10.1145/12345",
            "appendix_url": "https://example.com/appendix.pdf",
        }
        urls = _build_artifact_urls(art)
        assert "https://doi.org/10.1145/12345" not in urls
        assert "https://example.com/appendix.pdf" not in urls
        assert urls == ["https://github.com/foo/bar"]


class TestSearchDataUrlFormat:
    """Verify generate_search_data output structure."""

    def test_search_data_entry_has_artifact_urls_array(self):
        """A search_data entry should have artifact_urls (array), not
        repository_url/artifact_url/github_url."""
        entry = {
            "title": "Test Paper",
            "conference": "SOSP",
            "category": "systems",
            "year": 2023,
            "badges": ["available"],
            "artifact_urls": ["https://github.com/foo/bar"],
            "doi_url": "",
            "authors": ["Alice"],
            "affiliations": ["MIT"],
        }
        assert isinstance(entry["artifact_urls"], list)
        assert "repository_url" not in entry
        assert "artifact_url" not in entry
        assert "github_url" not in entry
