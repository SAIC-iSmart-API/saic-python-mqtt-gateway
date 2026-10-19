from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

import pytest

from handlers.command.base import RESULT_REFRESH_AND_CLEAR
from handlers.command.drivetrain.drivetrain_charging_cable_lock import (
    DrivetrainChargingCableLockCommand,
)


class TestDrivetrainChargingCableLockCommand(unittest.IsolatedAsyncioTestCase):
    async def test_lock_publishes_locked_state(self) -> None:
        vehicle_state = MagicMock()
        saic_api = AsyncMock()
        handler = DrivetrainChargingCableLockCommand(saic_api, vehicle_state)

        result = await handler.handle("true")

        assert result == RESULT_REFRESH_AND_CLEAR
        saic_api.control_charging_port_lock.assert_called_once_with(
            vehicle_state.vin, unlock=False
        )
        vehicle_state.update_charging_cable_lock.assert_called_once_with(locked=True)

    async def test_unlock_publishes_unlocked_state(self) -> None:
        vehicle_state = MagicMock()
        saic_api = AsyncMock()
        handler = DrivetrainChargingCableLockCommand(saic_api, vehicle_state)

        await handler.handle("false")

        saic_api.control_charging_port_lock.assert_called_once_with(
            vehicle_state.vin, unlock=True
        )
        vehicle_state.update_charging_cable_lock.assert_called_once_with(locked=False)

    async def test_failed_command_does_not_publish_state(self) -> None:
        vehicle_state = MagicMock()
        saic_api = AsyncMock()
        saic_api.control_charging_port_lock.side_effect = RuntimeError("boom")
        handler = DrivetrainChargingCableLockCommand(saic_api, vehicle_state)

        with pytest.raises(RuntimeError):
            await handler.handle("true")

        vehicle_state.update_charging_cable_lock.assert_not_called()
