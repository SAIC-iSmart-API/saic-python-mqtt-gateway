from __future__ import annotations

from typing import TYPE_CHECKING

from handlers.command.location.location_find_my_car import LocationFindMyCarCommand

if TYPE_CHECKING:
    from handlers.command import CommandHandlerBase

ALL_COMMAND_HANDLERS: list[type[CommandHandlerBase]] = [LocationFindMyCarCommand]
