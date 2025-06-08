from __future__ import annotations

from typing import TYPE_CHECKING

from handlers.command.climate.climate_back_window_heat import (
    ClimateBackWindowHeatCommand,
)
from handlers.command.climate.climate_front_window_heat import (
    ClimateFrontWindowHeatCommand,
)
from handlers.command.climate.climate_heated_seats_level import (
    ClimateHeatedSeatsFrontLeftLevelCommand,
    ClimateHeatedSeatsFrontRightLevelCommand,
)
from handlers.command.climate.climate_remote_climate_state import (
    ClimateRemoteClimateStateCommand,
)
from handlers.command.climate.climate_remote_temperature import (
    ClimateRemoteTemperatureCommand,
)

if TYPE_CHECKING:
    from handlers.command import CommandHandlerBase

ALL_COMMAND_HANDLERS: list[type[CommandHandlerBase]] = [
    ClimateBackWindowHeatCommand,
    ClimateFrontWindowHeatCommand,
    ClimateRemoteClimateStateCommand,
    ClimateRemoteTemperatureCommand,
    ClimateHeatedSeatsFrontLeftLevelCommand,
    ClimateHeatedSeatsFrontRightLevelCommand,
]
