from __future__ import annotations

import logging
from typing import override

from handlers.command.base import BooleanCommandHandler
from mqtt_topics import DRIVETRAIN_CHARGING_SET

LOG = logging.getLogger(__name__)


class DrivetrainChargingCommand(BooleanCommandHandler[None]):
    @classmethod
    @override
    def topic(cls) -> str:
        return DRIVETRAIN_CHARGING_SET

    @override
    async def handle_true(self) -> None:
        LOG.info("Charging will be started")
        await self.saic_api.control_charging(self.vin, stop_charging=False)

    @override
    async def handle_false(self) -> None:
        LOG.info("Charging will be stopped")
        await self.saic_api.control_charging(self.vin, stop_charging=True)
