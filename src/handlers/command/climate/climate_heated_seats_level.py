from __future__ import annotations

import logging
from typing import override

from exceptions import MqttGatewayException
from handlers.command.base import IntCommandHandler
import mqtt_topics

LOG = logging.getLogger(__name__)


class ClimateHeatedSeatsFrontLeftLevelCommand(IntCommandHandler):
    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.CLIMATE_HEATED_SEATS_FRONT_LEFT_LEVEL_SET

    @override
    async def handle_typed_payload(self, level: int) -> bool:
        try:
            LOG.info("Setting heated seats front left level to %d", level)
            changed = self.vehicle_state.update_heated_seats_front_left_level(level)
            if changed:
                await self.saic_api.control_heated_seats(
                    self.vin,
                    left_side_level=self.vehicle_state.remote_heated_seats_front_left_level,
                    right_side_level=self.vehicle_state.remote_heated_seats_front_right_level,
                )
            else:
                LOG.info("Heated seats front left level not changed")
        except Exception as e:
            msg = f"Error setting heated seats: {e}"
            raise MqttGatewayException(msg) from e
        return True


class ClimateHeatedSeatsFrontRightLevelCommand(IntCommandHandler):
    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.CLIMATE_HEATED_SEATS_FRONT_RIGHT_LEVEL_SET

    @override
    async def handle_typed_payload(self, level: int) -> bool:
        try:
            LOG.info("Setting heated seats front right level to %d", level)
            changed = self.vehicle_state.update_heated_seats_front_right_level(level)
            if changed:
                await self.saic_api.control_heated_seats(
                    self.vin,
                    left_side_level=self.vehicle_state.remote_heated_seats_front_left_level,
                    right_side_level=self.vehicle_state.remote_heated_seats_front_right_level,
                )
            else:
                LOG.info("Heated seats front right level not changed")
        except Exception as e:
            msg = f"Error setting heated seats: {e}"
            raise MqttGatewayException(msg) from e
        return True
