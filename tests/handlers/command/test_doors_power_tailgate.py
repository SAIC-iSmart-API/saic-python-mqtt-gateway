from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

import pytest
from saic_ismart_client_ng.api.vehicle.locks import TailgateAction
from saic_ismart_client_ng.api.vehicle.schema import VinInfo

from exceptions import MqttGatewayException
from handlers.command.base import RESULT_DO_NOTHING, RESULT_REFRESH_AND_CLEAR
from handlers.command.doors.doors_boot import DoorsBootCommand
from handlers.command.doors.doors_power_tailgate import DoorsPowerTailgateCommand
import mqtt_topics
from vehicle_info import VehicleInfo


def _make_vehicle_state(*, has_power_tailgate: bool) -> MagicMock:
    vin_info = VinInfo()
    vin_info.vin = "vin_test_000000000"
    vehicle_info = VehicleInfo(vin_info, None, has_power_tailgate=has_power_tailgate)

    vehicle_state = MagicMock()
    vehicle_state.vehicle = vehicle_info
    vehicle_state.vin = vehicle_info.vin
    return vehicle_state


class TestDoorsPowerTailgateCommand(unittest.IsolatedAsyncioTestCase):
    def test_topic(self) -> None:
        assert DoorsPowerTailgateCommand.topic() == "doors/boot/powerTailgate/set"
        assert DoorsPowerTailgateCommand.topic() != DoorsBootCommand.topic()
        assert (
            DoorsPowerTailgateCommand.topic()
            == mqtt_topics.DOORS_BOOT_POWER_TAILGATE_SET
        )

    async def test_open(self) -> None:
        vehicle_state = _make_vehicle_state(has_power_tailgate=True)
        saic_api = AsyncMock()
        handler = DoorsPowerTailgateCommand(saic_api, vehicle_state)

        result = await handler.handle("open")

        assert result == RESULT_REFRESH_AND_CLEAR
        saic_api.control_tailgate.assert_awaited_once_with(
            vehicle_state.vin, action=TailgateAction.OPEN
        )

    async def test_close(self) -> None:
        vehicle_state = _make_vehicle_state(has_power_tailgate=True)
        saic_api = AsyncMock()
        handler = DoorsPowerTailgateCommand(saic_api, vehicle_state)

        result = await handler.handle(" CLOSE ")

        assert result == RESULT_REFRESH_AND_CLEAR
        saic_api.control_tailgate.assert_awaited_once_with(
            vehicle_state.vin, action=TailgateAction.CLOSE
        )

    async def test_reject_when_not_enabled(self) -> None:
        vehicle_state = _make_vehicle_state(has_power_tailgate=False)
        saic_api = AsyncMock()
        handler = DoorsPowerTailgateCommand(saic_api, vehicle_state)

        with pytest.raises(MqttGatewayException, match="POWER_TAILGATE_VINS"):
            await handler.handle("open")

        saic_api.control_tailgate.assert_not_called()

    async def test_reject_unknown_payload(self) -> None:
        vehicle_state = _make_vehicle_state(has_power_tailgate=True)
        saic_api = AsyncMock()
        handler = DoorsPowerTailgateCommand(saic_api, vehicle_state)

        with pytest.raises(MqttGatewayException, match="Unsupported payload"):
            await handler.handle("true")

        saic_api.control_tailgate.assert_not_called()

    async def test_empty_payload_does_nothing(self) -> None:
        vehicle_state = _make_vehicle_state(has_power_tailgate=True)
        saic_api = AsyncMock()
        handler = DoorsPowerTailgateCommand(saic_api, vehicle_state)

        result = await handler.handle("")

        assert result == RESULT_DO_NOTHING
        saic_api.control_tailgate.assert_not_called()


class TestDoorsBootCommandUnchanged(unittest.IsolatedAsyncioTestCase):
    async def test_false_still_unlocks_the_latch(self) -> None:
        vehicle_state = _make_vehicle_state(has_power_tailgate=True)
        saic_api = AsyncMock()
        handler = DoorsBootCommand(saic_api, vehicle_state)

        result = await handler.handle("false")

        assert result == RESULT_REFRESH_AND_CLEAR
        saic_api.open_tailgate.assert_awaited_once_with(vehicle_state.vin)
        saic_api.control_tailgate.assert_not_called()
