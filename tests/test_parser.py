from __future__ import annotations

import argparse
from zoneinfo import ZoneInfo

import pytest

from configuration.argparse_extensions import check_timezone
from configuration.parser import process_command_line, setup_parser


def test_setup_parser_should_generate_a_valid_parser() -> None:
    parser = setup_parser()
    parser.print_help()


def test_check_timezone_accepts_iana_name() -> None:
    assert check_timezone("Australia/Sydney") == ZoneInfo("Australia/Sydney")


def test_check_timezone_accepts_gmt_offset() -> None:
    assert check_timezone("GMT+10:00") == ZoneInfo("Etc/GMT-10")


def test_check_timezone_rejects_invalid_value() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="not a valid timezone"):
        check_timezone("Not/A_Timezone")


def test_process_command_line_sets_forced_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "prog",
            "--saic-user",
            "user@example.com",
            "--saic-password",
            "secret",
            "--saic-user-timezone",
            "Australia/Sydney",
        ],
    )
    config = process_command_line()
    assert config.saic_user_timezone == ZoneInfo("Australia/Sydney")


def test_process_command_line_defaults_forced_timezone_to_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "prog",
            "--saic-user",
            "user@example.com",
            "--saic-password",
            "secret",
        ],
    )
    config = process_command_line()
    assert config.saic_user_timezone is None


def test_process_command_line_sets_device_app_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "prog",
            "--saic-user",
            "user@example.com",
            "--saic-password",
            "secret",
            "--saic-device-app-id",
            "com.example.app",
        ],
    )
    config = process_command_line()
    assert config.saic_device_app_id == "com.example.app"


def test_process_command_line_defaults_device_app_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "--saic-user", "user@example.com", "--saic-password", "secret"],
    )
    config = process_command_line()
    assert config.saic_device_app_id is None
    assert config.saic_preset == "mg_eu"


def test_process_command_line_sets_preset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "prog",
            "--saic-user",
            "user@example.com",
            "--saic-password",
            "secret",
            "--saic-preset",
            "maxus_eu",
        ],
    )
    config = process_command_line()
    assert config.saic_preset == "maxus_eu"
    assert config.saic_rest_uri is None


def test_process_command_line_rejects_unknown_preset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "prog",
            "--saic-user",
            "user@example.com",
            "--saic-password",
            "secret",
            "--saic-preset",
            "nope",
        ],
    )
    with pytest.raises(SystemExit):
        process_command_line()
