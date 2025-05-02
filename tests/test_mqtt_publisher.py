from __future__ import annotations

from typing import Any, override
import unittest

from configuration import Configuration, TransportProtocol
from publisher.core import MqttCommandListener
from publisher.mqtt_publisher import MqttPublisher

USER = "me@home.da"
VIN = "vin10000000000000"
DELAY = "42"
MODE = "periodic"
LOCK_STATE = "true"
REAR_WINDOW_HEAT_STATE = "on"


class TestMqttPublisher(unittest.IsolatedAsyncioTestCase, MqttCommandListener):
    @override
    async def on_mqtt_global_command_received(
        self, *, topic: str, payload: str
    ) -> None:
        pass

    @override
    async def on_mqtt_command_received(
        self, *, vin: str, topic: str, payload: str
    ) -> None:
        self.received_vin = vin
        self.received_payload = payload.strip().lower()

    @override
    def setUp(self) -> None:
        config = Configuration()
        config.mqtt_topic = "saic"
        config.saic_user = "user+a#b*c>d$e"
        config.mqtt_transport_protocol = TransportProtocol.TCP
        self.mqtt_client = MqttPublisher(config)
        self.mqtt_client.command_listener = self
        self.received_vin = ""
        self.received_payload = ""
        self.vehicle_base_topic = (
            f"{self.mqtt_client.configuration.mqtt_topic}/{USER}/vehicles/{VIN}"
        )

    def test_special_character_username(self) -> None:
        assert self.mqtt_client.get_mqtt_account_prefix() == "saic/user_a_b_c_d_e"

    async def test_update_mode(self) -> None:
        topic = "refresh/mode/set"
        full_topic = f"{self.vehicle_base_topic}/{topic}"
        await self.send_message(full_topic, MODE)
        assert self.received_vin == VIN
        assert self.received_payload == MODE

    async def test_update_lock_state(self) -> None:
        topic = "doors/locked/set"
        full_topic = f"{self.vehicle_base_topic}/{topic}"
        await self.send_message(full_topic, LOCK_STATE)
        assert self.received_vin == VIN
        assert self.received_payload == LOCK_STATE

    async def test_update_rear_window_heat_state(self) -> None:
        topic = "climate/rearWindowDefrosterHeating/set"
        full_topic = f"{self.vehicle_base_topic}/{topic}"
        await self.send_message(full_topic, REAR_WINDOW_HEAT_STATE)
        assert self.received_vin == VIN
        assert self.received_payload == REAR_WINDOW_HEAT_STATE

    async def send_message(self, topic: str, payload: Any) -> None:
        await self.mqtt_client.client.on_message("client", topic, payload, 0, {})

    async def on_charging_detected(self, vin: str) -> None:
        pass
