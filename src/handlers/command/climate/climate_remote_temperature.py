from __future__ import annotations

import logging
from typing import override

from exceptions import MqttGatewayException
from handlers.command.base import IntCommandHandler
import mqtt_topics

LOG = logging.getLogger(__name__)


class ClimateRemoteTemperatureCommand(IntCommandHandler):
    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.CLIMATE_REMOTE_TEMPERATURE_SET

    @override
    async def handle_typed_payload(self, temp: int) -> bool:
        try:
            LOG.info("Setting remote climate target temperature to %d", temp)
            changed = self.vehicle_state.set_ac_temperature(temp)
            if changed and self.vehicle_state.is_remote_ac_running:
                await self.saic_api.start_ac(
                    self.vin,
                    temperature_idx=self.vehicle_state.get_ac_temperature_idx(),
                )

        except ValueError as e:
            msg = f"Error setting temperature target: {e}"
            raise MqttGatewayException(msg) from e
        return True
