from __future__ import annotations

import logging
from typing import override

from handlers.command.base import (
    RESULT_DO_NOTHING,
    CommandProcessingResult,
    FloatCommandHandler,
)
import mqtt_topics

LOG = logging.getLogger(__name__)


class DrivetrainTotalBatteryCapacitySetCommand(FloatCommandHandler):
    @classmethod
    @override
    def is_replayable_when_retained(cls) -> bool:
        return True

    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.DRIVETRAIN_TOTAL_BATTERY_CAPACITY_SET

    @override
    async def handle_typed_payload(self, payload: float) -> CommandProcessingResult:
        LOG.info("Setting Total Battery Capacity to %f", payload)
        self.vehicle_state.update_battery_capacity(payload)

        # No need to force a refresh
        return RESULT_DO_NOTHING
