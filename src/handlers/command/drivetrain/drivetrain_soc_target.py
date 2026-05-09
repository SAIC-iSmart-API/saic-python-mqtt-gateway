from __future__ import annotations

import logging
from typing import override

from saic_ismart_client_ng.api.vehicle_charging import TargetBatteryCode

from handlers.command.base import (
    RESULT_DO_NOTHING,
    RESULT_REFRESH_ONLY,
    CommandProcessingResult,
    PayloadConvertingCommandHandler,
)
import mqtt_topics

LOG = logging.getLogger(__name__)


class DrivetrainSoCTargetCommand(PayloadConvertingCommandHandler[TargetBatteryCode]):
    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.DRIVETRAIN_SOC_TARGET_SET

    @property
    @override
    def state_topic(self) -> str:
        return mqtt_topics.DRIVETRAIN_SOC_TARGET

    @property
    @override
    def current_state(self) -> int | None:
        target = self.vehicle_state.target_soc
        return None if target is None else target.percentage

    @override
    def expected_state(self, raw_payload: str) -> int | None:
        try:
            return self.convert_payload(raw_payload).percentage
        except (ValueError, KeyError):
            return None

    @staticmethod
    @override
    def convert_payload(payload: str) -> TargetBatteryCode:
        percentage = int(payload.strip())
        return TargetBatteryCode.from_percentage(percentage)

    @override
    async def handle_typed_payload(
        self, target_battery_code: TargetBatteryCode
    ) -> CommandProcessingResult:
        if not self.vehicle_state.vehicle.supports_target_soc:
            LOG.warning(
                "Ignoring target SoC change: vehicle does not support target SoC"
            )
            return RESULT_DO_NOTHING
        LOG.info("Setting SoC target to %s", str(target_battery_code))
        await self.saic_api.set_target_battery_soc(
            self.vin, target_soc=target_battery_code
        )
        self.vehicle_state.update_target_soc(target_battery_code)
        return RESULT_REFRESH_ONLY
