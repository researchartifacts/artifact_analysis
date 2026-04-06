"""Tests for src.utils.conference – area classification and name helpers."""

from src.utils.conference import (
    ALL_CONFS,
    SECURITY_CONFS,
    SYSTEMS_CONFS,
    clean_name,
    conf_area,
    normalize_name,
    parse_conf_year,
)


class TestConfArea:
    def test_systems_conferences(self):
        for c in ("ATC", "EUROSYS", "FAST", "OSDI", "SC", "SOSP"):
            assert conf_area(c) == "systems"

    def test_security_conferences(self):
        for c in ("ACSAC", "CHES", "NDSS", "PETS", "SYSTEX", "USENIXSEC", "WOOT"):
            assert conf_area(c) == "security"

    def test_case_insensitive(self):
        assert conf_area("osdi") == "systems"
        assert conf_area("Ndss") == "security"

    def test_with_year_suffix(self):
        assert conf_area("osdi2024") == "systems"
        assert conf_area("usenixsec2023") == "security"

    def test_unknown(self):
        assert conf_area("FOOBAR") == "unknown"

    def test_all_confs_is_union(self):
        assert ALL_CONFS == SYSTEMS_CONFS | SECURITY_CONFS


class TestParseConfYear:
    def test_valid(self):
        assert parse_conf_year("osdi2024") == ("OSDI", 2024)
        assert parse_conf_year("NDSS2023") == ("NDSS", 2023)

    def test_no_year(self):
        name, year = parse_conf_year("OSDI")
        assert name == "OSDI"
        assert year is None

    def test_short_year(self):
        name, year = parse_conf_year("osdi24")
        assert name == "OSDI24"
        assert year is None  # only 4-digit years match


class TestCleanName:
    def test_strips_dblp_suffix(self):
        assert clean_name("Jane Doe 0001") == "Jane Doe"

    def test_collapses_whitespace(self):
        assert clean_name("Jane   Doe") == "Jane Doe"

    def test_empty(self):
        assert clean_name("") == ""

    def test_tabs_and_newlines(self):
        assert clean_name("Jane\tDoe\n") == "Jane Doe"


class TestNormalizeName:
    def test_lowercase_and_strip_accents(self):
        assert normalize_name("José García") == "jose garcia"

    def test_removes_dots(self):
        assert normalize_name("J. Smith") == "j smith"

    def test_strips_dblp_suffix(self):
        assert normalize_name("Jane Doe 0001") == "jane doe"

    def test_empty(self):
        assert normalize_name("") == ""

    def test_collapses_whitespace(self):
        assert normalize_name("  Jane   Doe  ") == "jane doe"
