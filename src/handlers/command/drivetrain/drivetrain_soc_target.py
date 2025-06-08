from __future__ import annotations

import logging
from typing import override

from saic_ismart_client_ng.api.vehicle_charging import TargetBatteryCode

from handlers.command.base import PayloadConvertingCommandHandler
import mqtt_topics

LOG = logging.getLogger(__name__)


class DrivetrainSoCTargetCommand(PayloadConvertingCommandHandler[TargetBatteryCode]):
    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.DRIVETRAIN_SOC_TARGET_SET

    @staticmethod
    @override
    def convert_payload(payload: str) -> TargetBatteryCode:
        percentage = int(payload.strip())
        return TargetBatteryCode.from_percentage(percentage)

    @override
    async def handle_typed_payload(
        self, target_battery_code: TargetBatteryCode
    ) -> bool:
        LOG.info("Setting SoC target to %s", str(target_battery_code))
        await self.saic_api.set_target_battery_soc(
            self.vin, target_soc=target_battery_code
        )
        self.vehicle_state.update_target_soc(target_battery_code)
        return True
