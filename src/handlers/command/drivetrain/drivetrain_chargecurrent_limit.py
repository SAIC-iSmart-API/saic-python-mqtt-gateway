from __future__ import annotations

import logging
from typing import override

from saic_ismart_client_ng.api.vehicle_charging import (
    ChargeCurrentLimitCode,
    TargetBatteryCode,
)

from handlers.command.base import (
    RESULT_REFRESH_ONLY,
    CommandProcessingResult,
    PayloadConvertingCommandHandler,
)
import mqtt_topics

LOG = logging.getLogger(__name__)


class DrivetrainChargeCurrentLimitCommand(
    PayloadConvertingCommandHandler[ChargeCurrentLimitCode]
):
    @classmethod
    def topic(cls) -> str:
        return mqtt_topics.DRIVETRAIN_CHARGECURRENT_LIMIT_SET

    @staticmethod
    @override
    def convert_payload(payload: str) -> ChargeCurrentLimitCode:
        raw_charge_current_limit = payload.strip().upper()
        return ChargeCurrentLimitCode.to_code(raw_charge_current_limit)

    @override
    async def handle_typed_payload(
        self, charge_current_limit: ChargeCurrentLimitCode
    ) -> CommandProcessingResult:
        LOG.info("Setting charging current limit to %s", str(charge_current_limit))
        await self.saic_api.set_target_battery_soc(
            self.vin,
            target_soc=self.__desired_target_soc,
            charge_current_limit=charge_current_limit,
        )
        self.vehicle_state.update_charge_current_limit(charge_current_limit)
        return RESULT_REFRESH_ONLY

    @property
    def __desired_target_soc(self) -> TargetBatteryCode:
        # Vehicles without target SoC support (e.g. LFP) must not receive a
        # target SoC in the charging settings request, or the vehicle rejects it.
        if not self.vehicle_state.vehicle.supports_target_soc:
            return TargetBatteryCode.P_IGNORE
        if (target_soc := self.vehicle_state.target_soc) is not None:
            return target_soc
        return TargetBatteryCode.P_IGNORE
