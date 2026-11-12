from __future__ import annotations

from typing import TYPE_CHECKING

from handlers.command.doors.doors_boot import DoorsBootCommand
from handlers.command.doors.doors_locked import DoorsLockedCommand
from handlers.command.doors.doors_power_tailgate import DoorsPowerTailgateCommand

if TYPE_CHECKING:
    from handlers.command import CommandHandlerBase

ALL_COMMAND_HANDLERS: list[type[CommandHandlerBase]] = [
    DoorsBootCommand,
    DoorsLockedCommand,
    DoorsPowerTailgateCommand,
]
