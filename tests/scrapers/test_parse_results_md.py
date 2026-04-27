"""Tests for src/scrapers/parse_results_md — HTML and markdown table parsers."""

from src.scrapers.parse_results_md import parse_html_results, parse_markdown_table_results


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
