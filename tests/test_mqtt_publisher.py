from __future__ import annotations

from typing import Any, override
import unittest
from unittest.mock import patch

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

    def test_publish_str_default_is_retained(self) -> None:
        with patch.object(self.mqtt_client.client, "publish") as m_pub:
            self.mqtt_client.publish_str("foo", "bar")
            m_pub.assert_called_once_with("saic/foo", "bar", retain=True)

    def test_publish_str_forwards_retain_false(self) -> None:
        with patch.object(self.mqtt_client.client, "publish") as m_pub:
            self.mqtt_client.publish_str("foo", "bar", retain=False)
            m_pub.assert_called_once_with("saic/foo", "bar", retain=False)

    def test_publish_int_default_is_retained(self) -> None:
        with patch.object(self.mqtt_client.client, "publish") as m_pub:
            self.mqtt_client.publish_int("foo", 42)
            m_pub.assert_called_once_with("saic/foo", 42, retain=True)

    def test_publish_int_forwards_retain_false(self) -> None:
        with patch.object(self.mqtt_client.client, "publish") as m_pub:
            self.mqtt_client.publish_int("foo", 42, retain=False)
            m_pub.assert_called_once_with("saic/foo", 42, retain=False)

    def test_publish_bool_default_is_retained(self) -> None:
        with patch.object(self.mqtt_client.client, "publish") as m_pub:
            self.mqtt_client.publish_bool("foo", True)
            m_pub.assert_called_once_with("saic/foo", True, retain=True)

    def test_publish_bool_forwards_retain_false(self) -> None:
        with patch.object(self.mqtt_client.client, "publish") as m_pub:
            self.mqtt_client.publish_bool("foo", True, retain=False)
            m_pub.assert_called_once_with("saic/foo", True, retain=False)

    def test_publish_float_default_is_retained(self) -> None:
        with patch.object(self.mqtt_client.client, "publish") as m_pub:
            self.mqtt_client.publish_float("foo", 1.5)
            m_pub.assert_called_once_with("saic/foo", 1.5, retain=True)

    def test_publish_float_forwards_retain_false(self) -> None:
        with patch.object(self.mqtt_client.client, "publish") as m_pub:
            self.mqtt_client.publish_float("foo", 1.5, retain=False)
            m_pub.assert_called_once_with("saic/foo", 1.5, retain=False)

    def test_publish_json_default_is_retained(self) -> None:
        with patch.object(self.mqtt_client.client, "publish") as m_pub:
            self.mqtt_client.publish_json("foo", {"a": 1})
            m_pub.assert_called_once()
            args, kwargs = m_pub.call_args
            assert args[0] == "saic/foo"
            assert kwargs == {"retain": True}

    def test_publish_json_forwards_retain_false(self) -> None:
        with patch.object(self.mqtt_client.client, "publish") as m_pub:
            self.mqtt_client.publish_json("foo", {"a": 1}, retain=False)
            m_pub.assert_called_once()
            args, kwargs = m_pub.call_args
            assert args[0] == "saic/foo"
            assert kwargs == {"retain": False}

    def test_clear_topic_publishes_none_retained(self) -> None:
        with patch.object(self.mqtt_client.client, "publish") as m_pub:
            self.mqtt_client.clear_topic("foo")
            m_pub.assert_called_once_with("saic/foo", None, retain=True)
