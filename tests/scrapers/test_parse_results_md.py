"""Tests for src/scrapers/parse_results_md — HTML/markdown and YAML normalization."""

from src.scrapers.parse_results_md import (
    _normalize_yaml_artifact_urls,
    parse_html_results,
    parse_markdown_table_results,
)


class TestParseHtmlResults:
    def test_basic_table(self):
        html = """
        <table>
          <tr>
            <td><a href="https://doi.org/10.1234">My Paper</a></td>
            <td><span id="aa">AVAILABLE</span> <span id="af">FUNCTIONAL</span></td>
            <td><a href="https://github.com/user/repo">Github</a></td>
          </tr>
        </table>
        """
        result = parse_html_results(html)
        assert len(result) == 1
        assert result[0]["title"] == "My Paper"
        assert "available" in result[0]["badges"]
        assert "functional" in result[0]["badges"]
        assert result[0]["repository_url"] == "https://github.com/user/repo"

    def test_reproduced_badge(self):
        html = """
        <table><tr>
          <td>Paper</td>
          <td><span id="rr">REPRODUCED</span></td>
          <td></td>
        </tr></table>
        """
        result = parse_html_results(html)
        assert "reproduced" in result[0]["badges"]

    def test_zenodo_url(self):
        html = """
        <table><tr>
          <td>Paper</td>
          <td><span id="aa">AVAILABLE</span></td>
          <td><a href="https://zenodo.org/record/123">Zenodo</a></td>
        </tr></table>
        """
        result = parse_html_results(html)
        assert result[0]["artifact_url"] == "https://zenodo.org/record/123"

    def test_paper_url_extracted(self):
        html = """
        <table><tr>
          <td><a href="https://doi.org/10.1234">My Paper</a></td>
          <td><span id="aa">AVAILABLE</span></td>
          <td></td>
        </tr></table>
        """
        result = parse_html_results(html)
        assert result[0]["paper_url"] == "https://doi.org/10.1234"

    def test_header_row_skipped(self):
        html = """
        <table>
          <tr><td>Paper Title</td><td>Badges</td><td>Links</td></tr>
          <tr><td>Real Paper</td><td><span id="aa">AVAILABLE</span></td><td></td></tr>
        </table>
        """
        result = parse_html_results(html)
        assert len(result) == 1
        assert result[0]["title"] == "Real Paper"

    def test_empty_table(self):
        assert parse_html_results("<table></table>") == []

    def test_no_badges_no_urls(self):
        html = """
        <table><tr>
          <td>Paper with nothing</td>
          <td></td>
          <td></td>
        </tr></table>
        """
        result = parse_html_results(html)
        assert len(result) == 0


class TestParseMarkdownTableResults:
    def test_basic_row(self):
        md = '| [My Paper](https://doi.org/10.1) | <span id="aa">AVAILABLE</span> | [Github](https://github.com/u/r) |'
        result = parse_markdown_table_results(md)
        assert len(result) == 1
        assert result[0]["title"] == "My Paper"
        assert "available" in result[0]["badges"]
        assert result[0]["repository_url"] == "https://github.com/u/r"

    def test_functional_and_reproduced(self):
        md = '| [P](url) | <span id="af">FUNCTIONAL</span><span id="rr">REPRODUCED</span> | |'
        result = parse_markdown_table_results(md)
        assert "functional" in result[0]["badges"]
        assert "reproduced" in result[0]["badges"]

    def test_separator_row_skipped(self):
        md = """| Paper | Badges | Links |
|:---:|:---:|:---:|
| [Real](u) | <span id="aa">AVAILABLE</span> | |"""
        result = parse_markdown_table_results(md)
        assert len(result) == 1

    def test_zenodo_link(self):
        md = '| [P](u) | <span id="aa">AVAILABLE</span> | [Zenodo](https://zenodo.org/record/1) |'
        result = parse_markdown_table_results(md)
        assert result[0]["artifact_url"] == "https://zenodo.org/record/1"

    def test_bare_github_url(self):
        md = '| [P](u) | <span id="aa">AVAILABLE</span> | https://github.com/user/repo |'
        result = parse_markdown_table_results(md)
        assert result[0]["repository_url"] == "https://github.com/user/repo"

    def test_no_link_in_title_skipped(self):
        md = "| No Link Here | <span>AVAILABLE</span> | |"
        result = parse_markdown_table_results(md)
        assert len(result) == 0


class TestYamlArtifactUrlNormalization:
    def test_splits_space_separated_artifact_url(self):
        artifact = {
            "title": "Measuring Popularity Of Cryptographic Libraries In Internet-wide Scans",
            "artifact_url": "https://crocs.fi.muni.cz/public/papers/acsac2017 https://github.com/crocs-muni/classifyRSAkey",
        }

        normalized = _normalize_yaml_artifact_urls(artifact)

        assert normalized["artifact_url"] == "https://crocs.fi.muni.cz/public/papers/acsac2017"
        assert normalized["artifact_urls"] == [
            "https://crocs.fi.muni.cz/public/papers/acsac2017",
            "https://github.com/crocs-muni/classifyRSAkey",
        ]

    def test_keeps_existing_artifact_urls_and_deduplicates(self):
        artifact = {
            "artifact_urls": [
                "https://github.com/example/repo",
                "https://doi.org/10.5281/zenodo.123",
            ],
            "artifact_url": "https://github.com/example/repo https://gitlab.com/example/repo",
        }

        normalized = _normalize_yaml_artifact_urls(artifact)

        assert normalized["artifact_urls"] == [
            "https://github.com/example/repo",
            "https://doi.org/10.5281/zenodo.123",
            "https://gitlab.com/example/repo",
        ]
        assert normalized["artifact_url"] == "https://github.com/example/repo"

    def test_resolves_base_urls_and_extra_urls(self):
        artifact = {
            "title": "Example",
            "artifact_url": "10.5281/zenodo.123",
            "artifact_extra_urls": ["https://github.com/example/repo"],
            "paper_url": "10.1145/1234.5678",
        }

        normalized = _normalize_yaml_artifact_urls(
            artifact,
            {"artifact_base_url": "https://doi.org/", "paper_base_url": "https://doi.org/"},
        )

        assert normalized["artifact_url"] == "https://doi.org/10.5281/zenodo.123"
        assert normalized["artifact_urls"] == [
            "https://doi.org/10.5281/zenodo.123",
            "https://github.com/example/repo",
        ]
        assert normalized["paper_url"] == "https://doi.org/10.1145/1234.5678"

    def test_ignores_missing_artifact_placeholder(self):
        normalized = _normalize_yaml_artifact_urls({"artifact_url": "MISSING"})

        assert "artifact_url" not in normalized
        assert "artifact_urls" not in normalized

    def test_preserves_legacy_sec_artifacts_fields(self):
        artifact = {
            "github_url": "https://github.com/example/repo",
            "doi": "10.1145/1234.5678",
            "additional_urls": ["https://example.com/archive"],
        }

        normalized = _normalize_yaml_artifact_urls(artifact)

        assert normalized == artifact
