from __future__ import annotations

from typing import TYPE_CHECKING

from handlers.command.gateway.refresh_mode import RefreshModeCommand
from handlers.command.gateway.refresh_period import (
    RefreshPeriodActiveCommand,
    RefreshPeriodAfterShutdownCommand,
    RefreshPeriodInactiveCommand,
    RefreshPeriodInactiveGraceCommand,
)

if TYPE_CHECKING:
    from handlers.command import CommandHandlerBase

ALL_COMMAND_HANDLERS: list[type[CommandHandlerBase]] = [
    RefreshModeCommand,
    RefreshPeriodActiveCommand,
    RefreshPeriodInactiveCommand,
    RefreshPeriodInactiveGraceCommand,
    RefreshPeriodAfterShutdownCommand,
]
