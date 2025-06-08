from __future__ import annotations

import logging
from typing import override

from saic_ismart_client_ng.api.vehicle_charging import ChrgPtcHeatResp

from handlers.command.base import BooleanCommandHandler
import mqtt_topics

LOG = logging.getLogger(__name__)


class DrivetrainBatteryHeatingCommand(BooleanCommandHandler[ChrgPtcHeatResp]):
    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.DRIVETRAIN_BATTERY_HEATING_SET

    @override
    async def handle_true(self) -> ChrgPtcHeatResp:
        LOG.info("Battery heater wil be will be switched on")
        return await self.saic_api.control_battery_heating(self.vin, enable=True)

    @override
    async def handle_false(self) -> ChrgPtcHeatResp:
        LOG.info("Battery heater wil be will be switched off")
        return await self.saic_api.control_battery_heating(self.vin, enable=False)

    @override
    async def should_refresh(self, response: ChrgPtcHeatResp | None) -> bool:
        if response is not None and response.ptcHeatResp is not None:
            decoded = response.heating_stop_reason
            self.publisher.publish_str(
                self.vehicle_state.get_topic(
                    mqtt_topics.DRIVETRAIN_BATTERY_HEATING_STOP_REASON
                ),
                f"UNKNOWN ({response.ptcHeatResp})"
                if decoded is None
                else decoded.name,
            )
        return True
