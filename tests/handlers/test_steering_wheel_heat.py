from __future__ import annotations

from dataclasses import asdict
import unittest
from unittest.mock import AsyncMock, MagicMock

from saic_ismart_client_ng import SaicApi
from saic_ismart_client_ng.exceptions import SaicApiException

from handlers.vehicle_command import VehicleCommandHandler
import mqtt_topics
from tests.common_mocks import VIN
from vehicle import RefreshMode

VEHICLE_PREFIX = f"vehicles/{VIN}"
SET_TOPIC = f"saic/{VEHICLE_PREFIX}/{mqtt_topics.CLIMATE_STEERING_WHEEL_HEAT_SET}"
RESULT_TOPIC = f"{VEHICLE_PREFIX}/{mqtt_topics.CLIMATE_STEERING_WHEEL_HEAT}/result"


class TestSteeringWheelHeatCommand(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.saic_api = AsyncMock(spec=SaicApi)
        self.vehicle_state = MagicMock()
        self.vehicle_state.vin = VIN
        self.vehicle_state.get_topic.side_effect = lambda t: f"{VEHICLE_PREFIX}/{t}"
        self.publisher = self.vehicle_state.publisher
        self.handler = VehicleCommandHandler(
            vehicle_state=self.vehicle_state,
            saic_api=self.saic_api,
            relogin_handler=AsyncMock(),
            mqtt_topic="saic",
            vehicle_prefix=VEHICLE_PREFIX,
        )

    async def test_on_sends_heating_request_and_refreshes(self) -> None:
        await self.handler.handle_mqtt_command(topic=SET_TOPIC, payload="on")

        self._assert_request("AQ==")
        self.publisher.publish_str.assert_any_call(
            RESULT_TOPIC, "Success", retain=False
        )
        self.publisher.clear_topic.assert_called_once_with(
            SET_TOPIC.removeprefix("saic/")
        )
        self.vehicle_state.set_refresh_mode.assert_called_once_with(
            RefreshMode.FORCE,
            f"after command execution on topic {mqtt_topics.CLIMATE_STEERING_WHEEL_HEAT_SET}",
        )

    async def test_off_sends_heating_request(self) -> None:
        await self.handler.handle_mqtt_command(topic=SET_TOPIC, payload="off")

        self._assert_request("AA==")

    async def test_failed_command_does_not_refresh(self) -> None:
        self.saic_api.send_vehicle_control_command.side_effect = SaicApiException(
            "unsupported"
        )

        await self.handler.handle_mqtt_command(topic=SET_TOPIC, payload="on")

        self.publisher.publish_str.assert_any_call(
            RESULT_TOPIC, "Failed: unsupported", retain=False
        )
        self.publisher.clear_topic.assert_not_called()
        self.vehicle_state.set_refresh_mode.assert_not_called()

    def _assert_request(self, encoded: str) -> None:
        self.saic_api.send_vehicle_control_command.assert_awaited_once()
        request, vin = self.saic_api.send_vehicle_control_command.call_args.args
        assert vin == VIN
        assert asdict(request) == {
            "vin": VIN,
            "rvcReqType": "8",
            "rvcParams": [{"paramId": 24, "paramValue": encoded}],
        }
