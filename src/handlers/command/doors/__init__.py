from __future__ import annotations

from typing import TYPE_CHECKING

from handlers.command.doors.doors_boot import DoorsBootCommand
from handlers.command.doors.doors_locked import DoorsLockedCommand

if TYPE_CHECKING:
    from handlers.command import CommandHandlerBase

ALL_COMMAND_HANDLERS: list[type[CommandHandlerBase]] = [
    DoorsBootCommand,
    DoorsLockedCommand,
]
