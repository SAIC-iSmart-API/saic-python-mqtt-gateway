from __future__ import annotations

from handlers.command.base import CommandHandlerBase
from handlers.command.climate import ALL_COMMAND_HANDLERS as CLIMATE_COMMAND_HANDLERS
from handlers.command.doors import ALL_COMMAND_HANDLERS as DOORS_COMMAND_HANDLERS
from handlers.command.drivetrain import (
    ALL_COMMAND_HANDLERS as DRIVETRAIN_COMMAND_HANDLERS,
)
from handlers.command.gateway import ALL_COMMAND_HANDLERS as GATEWAY_COMMAND_HANDLERS
from handlers.command.location import ALL_COMMAND_HANDLERS as LOCATION_COMMAND_HANDLERS

ALL_COMMAND_HANDLERS: list[type[CommandHandlerBase]] = [
    *CLIMATE_COMMAND_HANDLERS,
    *DOORS_COMMAND_HANDLERS,
    *DRIVETRAIN_COMMAND_HANDLERS,
    *GATEWAY_COMMAND_HANDLERS,
    *LOCATION_COMMAND_HANDLERS,
]

__all__ = ["ALL_COMMAND_HANDLERS", "CommandHandlerBase"]
