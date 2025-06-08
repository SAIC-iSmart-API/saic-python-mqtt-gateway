from __future__ import annotations

from typing import TYPE_CHECKING

from handlers.command.drivetrain.drivetrain_battery_heating import (
    DrivetrainBatteryHeatingCommand,
)
from handlers.command.drivetrain.drivetrain_battery_heating_schedule import (
    DrivetrainBatteryHeatingScheduleCommand,
)
from handlers.command.drivetrain.drivetrain_chargecurrent_limit import (
    DrivetrainChargeCurrentLimitCommand,
)
from handlers.command.drivetrain.drivetrain_charging import DrivetrainChargingCommand
from handlers.command.drivetrain.drivetrain_charging_cable_lock import (
    DrivetrainChargingCableLockCommand,
)
from handlers.command.drivetrain.drivetrain_charging_schedule import (
    DrivetrainChargingScheduleCommand,
)
from handlers.command.drivetrain.drivetrain_hv_battery_active import (
    DrivetrainHVBatteryActiveCommand,
)
from handlers.command.drivetrain.drivetrain_soc_target import DrivetrainSoCTargetCommand

if TYPE_CHECKING:
    from handlers.command import CommandHandlerBase

ALL_COMMAND_HANDLERS: list[type[CommandHandlerBase]] = [
    DrivetrainBatteryHeatingCommand,
    DrivetrainBatteryHeatingScheduleCommand,
    DrivetrainChargeCurrentLimitCommand,
    DrivetrainChargingCommand,
    DrivetrainHVBatteryActiveCommand,
    DrivetrainSoCTargetCommand,
    DrivetrainChargingScheduleCommand,
    DrivetrainChargingCableLockCommand,
]
