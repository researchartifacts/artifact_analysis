"""Tests for src.utils.logging_config — logging setup helpers."""

import argparse
import logging

from src.utils.logging_config import LOG_LEVELS, add_log_level_arg, setup_logging


class TestLogLevels:
    def test_maps_standard_levels(self):
        assert LOG_LEVELS["debug"] == logging.DEBUG
        assert LOG_LEVELS["info"] == logging.INFO
        assert LOG_LEVELS["warning"] == logging.WARNING
        assert LOG_LEVELS["error"] == logging.ERROR


class TestAddLogLevelArg:
    def test_adds_log_level_argument(self):
        parser = argparse.ArgumentParser()
        add_log_level_arg(parser)
        args = parser.parse_args(["--log-level", "debug"])
        assert args.log_level == "debug"

    def test_default_is_info(self):
        parser = argparse.ArgumentParser()
        add_log_level_arg(parser)
        args = parser.parse_args([])
        assert args.log_level == "info"

    def test_rejects_invalid_level(self):
        parser = argparse.ArgumentParser()
        add_log_level_arg(parser)
        import pytest

        with pytest.raises(SystemExit):
            parser.parse_args(["--log-level", "verbose"])


class TestSetupLogging:
    def _reset_root_logger(self):
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.NOTSET)

    def test_accepts_int_level(self):
        self._reset_root_logger()
        setup_logging(logging.DEBUG)
        assert logging.root.level == logging.DEBUG

    def test_accepts_string_level(self):
        self._reset_root_logger()
        setup_logging("warning")
        assert logging.root.level == logging.WARNING

    def test_unknown_string_defaults_to_info(self):
        self._reset_root_logger()
        setup_logging("bogus")
        assert logging.root.level == logging.INFO
