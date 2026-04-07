"""
Shared conference metadata, area classification, and name-normalization helpers.

Every generator / enricher should import from here rather than redefining
its own ``SYSTEMS_CONFS``, ``SECURITY_CONFS``, ``_conf_area()``,
``_extract_conf_year()``, or name-cleaning functions.
"""

from __future__ import annotations

import re
import unicodedata

# ── Conference → area classification ────────────────────────────────────────
# Canonical source: researchartifacts.github.io/_data/summary.yml
# SysTEX is a security workshop co-located with systems venues.

SYSTEMS_CONFS = frozenset(
    {
        "ATC",
        "EUROSYS",
        "FAST",
        "OSDI",
        "SC",
        "SOSP",
    }
)

SECURITY_CONFS = frozenset(
    {
        "ACSAC",
        "CHES",
        "NDSS",
        "PETS",
        "SYSTEX",
        "USENIXSEC",
        "WOOT",
    }
)

ALL_CONFS = SYSTEMS_CONFS | SECURITY_CONFS


def conf_area(conf_name: str) -> str:
    """Return ``'systems'``, ``'security'``, or ``'unknown'``.

    Accepts a bare conference name (``'OSDI'``) **or** a conf-year string
    (``'osdi2024'``).  Any casing is accepted.
    """
    upper = re.sub(r"\d+$", "", conf_name).strip().upper()
    if upper in SYSTEMS_CONFS:
        return "systems"
    if upper in SECURITY_CONFS:
        return "security"
    return "unknown"


# ── Conference-year string parsing ──────────────────────────────────────────

_CONF_YEAR_RE = re.compile(r"^([a-zA-Z]+)(\d{4})$")


def parse_conf_year(conf_year_str: str) -> tuple[str, int | None]:
    """Parse ``'osdi2024'`` → ``('OSDI', 2024)``.

    Returns ``(name_upper, year_int)`` on success, or
    ``(conf_year_str.upper(), None)`` on failure.
    """
    m = _CONF_YEAR_RE.match(conf_year_str)
    if m:
        return m.group(1).upper(), int(m.group(2))
    return conf_year_str.upper(), None


# ── Author / person name normalisation ──────────────────────────────────────


def clean_name(name: str) -> str:
    """Remove DBLP disambiguation suffixes and collapse whitespace.

    ``'Jane Doe 0001'`` → ``'Jane Doe'``
    """
    if not name:
        return ""
    name = re.sub(r"[\t\n\r]+", " ", name)
    name = re.sub(r"\s+\d{4}$", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def normalize_name(name: str) -> str:
    """Aggressive normalisation for cross-source matching.

    Lower-cases, strips accents, removes dots, collapses whitespace.
    """
    if not name:
        return ""
    name = name.strip().lower()
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = re.sub(r"\.", "", name)
    name = re.sub(r"\s+\d{4}$", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def normalize_title(title: str) -> str:
    """Normalize a paper title for fuzzy matching.

    Lower-cases, strips punctuation (keeping word chars and spaces),
    and collapses whitespace.  Used for deduplication and cross-source
    title matching.
    """
    if not title:
        return ""
    return " ".join(re.sub(r"[^\w\s]", "", title.lower()).split())


# ── Committee member cleaning ────────────────────────────────────────────────

PLACEHOLDER_NAMES = frozenset({"you?", "you", "tba", "tbd", "n/a", "", "title: organizers"})

_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_BR_TAG = re.compile(r"<br\s*/?>$")


def clean_member_name(raw_name: str) -> str | None:
    """Clean a committee member name.

    Strips markdown links, trailing ``<br>`` tags, and skips placeholder names.
    Returns the cleaned name, or ``None`` if the entry should be dropped.
    """
    name = raw_name.strip()
    link_match = _MARKDOWN_LINK.match(name)
    if link_match:
        name = link_match.group(1)
    name = _BR_TAG.sub("", name).strip()
    if name.lower() in PLACEHOLDER_NAMES or len(name) <= 1:
        return None
    if "contact" in name.lower() or "reach" in name.lower() or "mailto:" in name.lower():
        return None
    return clean_name(name)
