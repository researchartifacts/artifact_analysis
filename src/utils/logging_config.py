"""Centralized logging configuration for the ReproDB pipeline."""

import argparse
import logging
import sys

logger = logging.getLogger(__name__)

LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


def add_log_level_arg(parser: argparse.ArgumentParser) -> None:
    """Add a ``--log-level`` argument to an argparse parser."""
    parser.add_argument(
        "--log-level",
        choices=LOG_LEVELS,
        default="info",
        help="Set logging verbosity (default: info)",
    )


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger with a consistent format.

    Call once from each script's ``if __name__ == "__main__"`` block.
    from src.utils.logging_config import setup_logging
    setup_logging()

    Accepts either an ``int`` (e.g. ``logging.DEBUG``) or a ``str``
    name (e.g. ``"debug"``).
    """
    if isinstance(level, str):
        level = LOG_LEVELS.get(level.lower(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(message)s",
        stream=sys.stdout,
    )
