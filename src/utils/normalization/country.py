"""Shared country normalization helpers.

Provides consistent conversion between human-friendly country names and
ISO 3166-1 alpha-2 codes across the pipeline.
"""

from __future__ import annotations

import pycountry

# Canonical display names used in this project for selected ISO codes.
ISO2_TO_DISPLAY_OVERRIDES: dict[str, str] = {
    "TW": "Taiwan",
    "HK": "Hong Kong",
    "MO": "Macau",
    "KR": "South Korea",
    "KP": "North Korea",
}

# Reverse map for common country names that pycountry.lookup may not normalize
# to our preferred short forms or that need deterministic behavior.
DISPLAY_TO_ISO2_OVERRIDES: dict[str, str] = {
    "Russia": "RU",
    "South Korea": "KR",
    "North Korea": "KP",
    "Taiwan": "TW",
    "Hong Kong": "HK",
    "Macau": "MO",
    "Iran": "IR",
    "Syria": "SY",
    "Venezuela": "VE",
    "Bolivia": "BO",
    "Tanzania": "TZ",
    "Vietnam": "VN",
}


def iso2_to_country_name(country_code: str) -> str | None:
    """Convert ISO alpha-2 code to a canonical country display name."""
    code = (country_code or "").strip().upper()
    if not code:
        return None

    override = ISO2_TO_DISPLAY_OVERRIDES.get(code)
    if override:
        return override

    rec = pycountry.countries.get(alpha_2=code)
    if rec is None:
        return None
    name = getattr(rec, "name", None)
    return name if isinstance(name, str) else None


def country_name_to_iso2(country_name: str) -> str | None:
    """Convert a country display/official name to ISO alpha-2 code."""
    name = (country_name or "").strip()
    if not name:
        return None

    override = DISPLAY_TO_ISO2_OVERRIDES.get(name)
    if override:
        return override

    try:
        rec = pycountry.countries.lookup(name)
    except LookupError:
        return None

    code = getattr(rec, "alpha_2", None)
    return code if isinstance(code, str) else None
