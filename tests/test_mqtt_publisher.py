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
        self, *, vin: str, topic: str, payload: str, retained: bool = False
    ) -> None:
        self.received_vin = vin
        self.received_payload = payload.strip().lower()
        self.received_retained = retained

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
        self.received_retained = False
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

    async def test_get_vin_from_sanitized_topic(self) -> None:
        """Topics arrive with the sanitized prefix, not the raw username."""
        sanitized_prefix = self.mqtt_client.get_mqtt_account_prefix()
        topic = f"{sanitized_prefix}/vehicles/{VIN}/refresh/mode/set"
        await self.send_message(topic, MODE)
        assert self.received_vin == VIN
        assert self.received_payload == MODE

    def test_get_vin_from_topic_uses_sanitized_prefix(self) -> None:
        """get_vin_from_topic should work with sanitized topics."""
        sanitized_prefix = self.mqtt_client.get_mqtt_account_prefix()
        topic = f"{sanitized_prefix}/vehicles/{VIN}/refresh/mode/set"
        assert self.mqtt_client.get_vin_from_topic(topic) == VIN

    async def on_charging_detected(self, vin: str) -> None:
        pass

    async def on_charging_station_energy_imported(
        self, vin: str, imported_energy_wh: float
    ) -> None:
        pass

    async def on_charger_connection_state_changed(
        self, vin: str, connected: bool
    ) -> None:
        pass
