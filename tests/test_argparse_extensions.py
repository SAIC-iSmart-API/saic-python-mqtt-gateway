from __future__ import annotations

import argparse

import pytest

from configuration.argparse_extensions import EnvDefault


class DummyParser(argparse.ArgumentParser):
    """Dummy ArgumentParser for testing purposes."""

    def __init__(self) -> None:
        super().__init__(add_help=False)


@pytest.fixture(name="mock_envdefault_file")
def setup_fixture_mock_envdefault_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock the _get_default_from_file method to return a fixed value."""
    monkeypatch.setattr(
        "configuration.argparse_extensions.EnvDefault._get_default_from_file",
        lambda *_, **__: "file_env_value",
    )


@pytest.fixture(name="mock_env")
def setup_fixture_mock_env(monkeypatch: pytest.MonkeyPatch) -> None:  # pylint: disable=unused-argument
    """Mock the environment variable to return a fixed value."""


# pylint: disable-next=unused-argument
def test_envdefault_envvar(
    monkeypatch: pytest.MonkeyPatch,
    mock_envdefault_file: None,  # noqa: ARG001 #pylint: disable=unused-argument
) -> None:
    """Retrieves the value from an environment variable."""
    monkeypatch.setenv("TEST_ENV", "env_value")
    parser = DummyParser()
    parser.add_argument("--test", action=EnvDefault, envvar="TEST_ENV", required=False)
    args = parser.parse_args([])
    assert args.test == "env_value"


def test_envdefault_file_envvar(
    monkeypatch: pytest.MonkeyPatch,
    mock_envdefault_file: None,  # noqa: ARG001 pylint: disable=unused-argument
) -> None:
    """Retrieve the value from a file specified by an environment variable."""
    monkeypatch.setenv("TEST_ENV_FILE", "file_env_value")
    parser = DummyParser()
    parser.add_argument(
        "--test",
        action=EnvDefault,
        try_file=True,
        envvar="TEST_ENV",
        required=False,
    )
    args = parser.parse_args([])
    assert args.test == "file_env_value"


def test_envdefault_priority(
    monkeypatch: pytest.MonkeyPatch,
    mock_envdefault_file: None,  # noqa: ARG001 pylint: disable=unused-argument
) -> None:
    """Prioritize environment variable over file."""
    monkeypatch.setenv("TEST_ENV", "env_value")
    monkeypatch.setenv("TEST_ENV_FILE", "file_env_value")

    parser = DummyParser()
    parser.add_argument(
        "--test",
        action=EnvDefault,
        try_file=True,
        envvar="TEST_ENV",
        required=False,
    )
