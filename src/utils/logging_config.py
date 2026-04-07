"""Centralized logging configuration for the ReproDB pipeline."""

import logging
import sys

logger = logging.getLogger(__name__)


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger with a consistent format.

    Call once from each script's ``if __name__ == "__main__"`` block.
    from src.utils.logging_config import setup_logging
    setup_logging()

    The format mirrors plain ``logger.info()`` output so existing downstream
    tooling (CI logs, etc.) continues to work unchanged.
    """
    logging.basicConfig(
        level=level,
        format="%(message)s",
        stream=sys.stdout,
    )
