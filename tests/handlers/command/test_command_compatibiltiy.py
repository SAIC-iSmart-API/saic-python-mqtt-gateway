from __future__ import annotations

import pytest

from handlers.command import ALL_COMMAND_HANDLERS, CommandHandlerBase
from mqtt_topics import SET_SUFFIX


@pytest.mark.parametrize("test_class", ALL_COMMAND_HANDLERS)
def test_all_commands_should_have_a_valid_name(
    test_class: type[CommandHandlerBase],
) -> None:
    command_name = test_class.name()
    assert command_name is not None
    assert len(command_name) > 0
    assert command_name.endswith("Command")


@pytest.mark.parametrize("test_class", ALL_COMMAND_HANDLERS)
def test_all_commands_should_have_a_valid_topic(
    test_class: type[CommandHandlerBase],
) -> None:
    command_topic = test_class.topic()
    assert command_topic is not None
    assert len(command_topic) > 0
    assert command_topic.endswith(SET_SUFFIX)


def test_there_should_be_no_duplicate_command_names() -> None:
    discovered_names = [x.name for x in ALL_COMMAND_HANDLERS]
    assert len(discovered_names) == len(set(discovered_names))


def test_there_should_be_no_duplicate_command_topics() -> None:
    discovered_names = [x.topic for x in ALL_COMMAND_HANDLERS]
    assert len(discovered_names) == len(set(discovered_names))
