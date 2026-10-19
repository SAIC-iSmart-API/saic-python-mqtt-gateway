from __future__ import annotations

import logging
from typing import override

from handlers.command.base import (
    RESULT_REFRESH_AND_CLEAR,
    BooleanCommandHandler,
    CommandProcessingResult,
)
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
        # Some models never report the lock state, so publish the commanded one.
        # Models that do report it overwrite it on the forced refresh.
        self.vehicle_state.update_charging_cable_lock(locked=True)

    @override
    async def handle_false(self) -> None:
        LOG.info(f"Vehicle {self.vin} charging cable will be unlocked")
        await self.saic_api.control_charging_port_lock(self.vin, unlock=True)
        self.vehicle_state.update_charging_cable_lock(locked=False)

    @override
    async def _get_action_result(self, _action_result: None) -> CommandProcessingResult:
        return RESULT_REFRESH_AND_CLEAR
