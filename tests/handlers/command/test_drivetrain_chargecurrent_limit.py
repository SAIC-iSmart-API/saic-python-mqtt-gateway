from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from saic_ismart_client_ng.api.vehicle_charging import TargetBatteryCode

from handlers.command.base import RESULT_REFRESH_ONLY
from handlers.command.drivetrain.drivetrain_chargecurrent_limit import (
    DrivetrainChargeCurrentLimitCommand,
)
from tests.common_mocks import make_vehicle_state_with_target_soc_support

EXPECTED_LIMIT = DrivetrainChargeCurrentLimitCommand.convert_payload("16A")


class TestDrivetrainChargeCurrentLimitTargetSoc(unittest.IsolatedAsyncioTestCase):
    async def test_lfp_vehicle_sends_ignore_target_soc(self) -> None:
        vehicle_state = make_vehicle_state_with_target_soc_support(
            supports_target_soc=False
        )
        vehicle_state.target_soc = TargetBatteryCode.P_80
        saic_api = AsyncMock()
        handler = DrivetrainChargeCurrentLimitCommand(saic_api, vehicle_state)

        result = await handler.handle("16A")

        assert result == RESULT_REFRESH_ONLY
        saic_api.set_target_battery_soc.assert_called_once_with(
            vehicle_state.vin,
            target_soc=TargetBatteryCode.P_IGNORE,
            charge_current_limit=EXPECTED_LIMIT,
        )

    async def test_nmc_vehicle_keeps_known_target_soc(self) -> None:
        vehicle_state = make_vehicle_state_with_target_soc_support(
            supports_target_soc=True
        )
        vehicle_state.target_soc = TargetBatteryCode.P_80
        saic_api = AsyncMock()
        handler = DrivetrainChargeCurrentLimitCommand(saic_api, vehicle_state)

        await handler.handle("16A")

        saic_api.set_target_battery_soc.assert_called_once_with(
            vehicle_state.vin,
            target_soc=TargetBatteryCode.P_80,
            charge_current_limit=EXPECTED_LIMIT,
        )
