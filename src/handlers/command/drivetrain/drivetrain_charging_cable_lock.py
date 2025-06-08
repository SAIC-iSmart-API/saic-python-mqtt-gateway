from __future__ import annotations

import logging
from typing import override

from handlers.command.base import BooleanCommandHandler
import mqtt_topics

LOG = logging.getLogger(__name__)


class DrivetrainChargingCableLockCommand(BooleanCommandHandler[None]):
    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.DRIVETRAIN_CHARGING_CABLE_LOCK_SET

    @override
    async def handle_true(self) -> None:
        LOG.info(f"Vehicle {self.vin} charging cable will be locked")
        await self.saic_api.control_charging_port_lock(self.vin, unlock=False)

    @override
    async def handle_false(self) -> None:
        LOG.info(f"Vehicle {self.vin} charging cable will be unlocked")
        await self.saic_api.control_charging_port_lock(self.vin, unlock=True)
