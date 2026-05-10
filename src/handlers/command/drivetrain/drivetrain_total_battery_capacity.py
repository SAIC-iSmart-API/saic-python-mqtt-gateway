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

        # The HA number and sensor entities share the same state topic.
        # Republish the effective capacity locally so the sensor reflects
        # the change immediately instead of waiting for the next vehicle poll
        # (payload of 0 falls back to the per-model default in real_battery_capacity).
        effective_capacity = self.vehicle_state.vehicle.real_battery_capacity
        if effective_capacity is not None and effective_capacity > 0:
            self.publisher.publish_float(
                self.vehicle_state.get_topic(
                    mqtt_topics.DRIVETRAIN_TOTAL_BATTERY_CAPACITY
                ),
                effective_capacity,
            )

        # No need to force a refresh
        return RESULT_DO_NOTHING
