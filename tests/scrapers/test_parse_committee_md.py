"""Tests for src/scrapers/parse_committee_md — committee line parser."""

from src.scrapers.parse_committee_md import _parse_member_line


class TestParseMemberLine:
    def test_name_comma_affiliation(self):
        name, aff = _parse_member_line("Alice Smith, MIT")
        assert name == "Alice Smith"
        assert aff == "MIT"

    def test_name_paren_affiliation(self):
        name, aff = _parse_member_line("Alice Smith (MIT)")
        assert name == "Alice Smith"
        assert aff == "MIT"

    def test_name_comma_detail_paren_affiliation(self):
        name, aff = _parse_member_line("Salvatore Signorello, INESC-ID/IST (University of Lisbon)")
        assert name == "Salvatore Signorello"
        assert aff == "University of Lisbon"

    def test_list_marker_dash(self):
        name, aff = _parse_member_line("- Alice Smith, MIT")
        assert name == "Alice Smith"
        assert aff == "MIT"

    def test_list_marker_star(self):
        name, aff = _parse_member_line("* Alice Smith, MIT")
        assert name == "Alice Smith"
        assert aff == "MIT"

    def test_markdown_link(self):
        name, aff = _parse_member_line("[Alice Smith](https://example.com), MIT")
        assert name == "Alice Smith"
        assert aff == "MIT"

    def test_bold_markers_stripped(self):
        name, aff = _parse_member_line("**Alice Smith**, MIT")
        assert name == "Alice Smith"
        assert aff == "MIT"

    def test_empty_line(self):
        assert _parse_member_line("") == (None, None)

    def test_heading_skipped(self):
        assert _parse_member_line("# Chairs") == (None, None)

    def test_separator_skipped(self):
        assert _parse_member_line("---") == (None, None)

    def test_contact_line_skipped(self):
        assert _parse_member_line("Please contact us at ae-chairs@conf.org") == (None, None)

    def test_footnote_skipped(self):
        assert _parse_member_line("¹ Best paper award") == (None, None)

    def test_award_line_skipped(self):
        assert _parse_member_line("Distinguished Artifact Award") == (None, None)

    def test_placeholder_skipped(self):
        assert _parse_member_line("- You?") == (None, None)

    def test_tba_skipped(self):
        assert _parse_member_line("- TBA") == (None, None)

    def test_single_char_skipped(self):
        assert _parse_member_line("X") == (None, None)

    def test_name_only(self):
        name, aff = _parse_member_line("Alice Smith")
        assert name == "Alice Smith"
        assert aff == ""

    def test_trailing_br_stripped(self):
        name, aff = _parse_member_line("Alice Smith, MIT <br>")
        assert name == "Alice Smith"
        assert aff == "MIT"

    def test_trailing_br_self_closing(self):
        name, aff = _parse_member_line("Alice Smith, MIT <br/>")
        assert name == "Alice Smith"
        assert aff == "MIT"

    def test_footnote_marker_stripped(self):
        name, aff = _parse_member_line("Cen Zhang (Georgia Tech)¹")
        assert name == "Cen Zhang"
        assert aff == "Georgia Tech"
