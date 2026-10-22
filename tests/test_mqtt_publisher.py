from __future__ import annotations

import asyncio
from contextlib import suppress
import json
from typing import Any, override
import unittest
from unittest.mock import AsyncMock, patch

import pytest

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
        await self.mqtt_client._on_message("client", topic, payload, 0, False)

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

    async def _call_and_flush(self, fn: Any, *args: Any, **kwargs: Any) -> AsyncMock:
        mock = AsyncMock()
        with patch.object(self.mqtt_client, "_MqttPublisher__async_publish", mock):
            self.mqtt_client._MqttPublisher__connected.set()  # type: ignore[attr-defined]
            fn(*args, **kwargs)
            await asyncio.sleep(0)
        return mock

    async def test_publish_str_default_is_retained(self) -> None:
        m = await self._call_and_flush(self.mqtt_client.publish_str, "foo", "bar")
        m.assert_called_once_with("saic/foo", "bar", retain=True, qos=0)

    async def test_publish_runs_as_background_task(self) -> None:
        pending = self.mqtt_client._MqttPublisher__background_tasks  # type: ignore[attr-defined]
        with patch.object(
            self.mqtt_client, "_MqttPublisher__async_publish", AsyncMock()
        ) as publish:
            self.mqtt_client.publish_str("foo", "bar")
            assert len(pending) == 1
            await pending.wait()
        publish.assert_awaited_once()
        assert len(pending) == 0

    async def test_enable_commands_runs_as_background_task(self) -> None:
        pending = self.mqtt_client._MqttPublisher__background_tasks  # type: ignore[attr-defined]
        self.mqtt_client.enable_commands()
        assert len(pending) == 1
        await pending.wait()
        assert len(pending) == 0

    async def test_publish_str_outside_event_loop_raises_clear_error(self) -> None:
        with pytest.raises(RuntimeError, match="outside the event loop thread"):
            await asyncio.to_thread(self.mqtt_client.publish_str, "foo", "bar")

    async def test_publish_str_forwards_retain_false(self) -> None:
        m = await self._call_and_flush(
            self.mqtt_client.publish_str, "foo", "bar", retain=False
        )
        m.assert_called_once_with("saic/foo", "bar", retain=False, qos=0)

    async def test_publish_int_default_is_retained(self) -> None:
        m = await self._call_and_flush(self.mqtt_client.publish_int, "foo", 42)
        m.assert_called_once_with("saic/foo", 42, retain=True, qos=0)

    async def test_publish_int_forwards_retain_false(self) -> None:
        m = await self._call_and_flush(
            self.mqtt_client.publish_int, "foo", 42, retain=False
        )
        m.assert_called_once_with("saic/foo", 42, retain=False, qos=0)

    async def test_publish_bool_default_is_retained(self) -> None:
        m = await self._call_and_flush(self.mqtt_client.publish_bool, "foo", True)
        m.assert_called_once_with("saic/foo", True, retain=True, qos=0)

    async def test_publish_bool_forwards_retain_false(self) -> None:
        m = await self._call_and_flush(
            self.mqtt_client.publish_bool, "foo", True, retain=False
        )
        m.assert_called_once_with("saic/foo", True, retain=False, qos=0)

    async def test_publish_float_default_is_retained(self) -> None:
        m = await self._call_and_flush(self.mqtt_client.publish_float, "foo", 1.5)
        m.assert_called_once_with("saic/foo", 1.5, retain=True, qos=0)

    async def test_publish_float_forwards_retain_false(self) -> None:
        m = await self._call_and_flush(
            self.mqtt_client.publish_float, "foo", 1.5, retain=False
        )
        m.assert_called_once_with("saic/foo", 1.5, retain=False, qos=0)

    async def test_publish_json_default_is_retained(self) -> None:
        m = await self._call_and_flush(self.mqtt_client.publish_json, "foo", {"a": 1})
        m.assert_called_once()
        args, kwargs = m.call_args
        assert args[0] == "saic/foo"
        assert json.loads(args[1]) == {"a": 1}
        assert kwargs == {"retain": True, "qos": 0}

    async def test_publish_json_forwards_retain_false(self) -> None:
        m = await self._call_and_flush(
            self.mqtt_client.publish_json, "foo", {"a": 1}, retain=False
        )
        m.assert_called_once()
        args, kwargs = m.call_args
        assert args[0] == "saic/foo"
        assert json.loads(args[1]) == {"a": 1}
        assert kwargs == {"retain": False, "qos": 0}

    async def test_clear_topic_publishes_none_retained(self) -> None:
        m = await self._call_and_flush(self.mqtt_client.clear_topic, "foo")
        m.assert_called_once_with("saic/foo", None, retain=True, qos=0)

    async def _connect_and_capture_client_kwargs(
        self, config: Configuration
    ) -> dict[str, Any]:
        publisher = MqttPublisher(config)
        with patch("publisher.mqtt_publisher.aiomqtt.Client") as client_cls:
            client_cls.return_value.__aenter__.side_effect = asyncio.CancelledError
            connect_task = asyncio.get_running_loop().create_task(publisher.connect())
            for _ in range(20):
                await asyncio.sleep(0)
                if client_cls.call_args is not None:
                    break
            connect_task.cancel()
            with suppress(asyncio.CancelledError):
                await connect_task
            assert client_cls.call_args is not None
            return dict(client_cls.call_args.kwargs)

    async def test_connect_raises_when_loop_crashes_before_connecting(self) -> None:
        """An unexpected error in the MQTT loop must not hang connect() forever."""
        config = Configuration()
        config.mqtt_host = "localhost"
        config.mqtt_transport_protocol = TransportProtocol.TCP
        publisher = MqttPublisher(config)
        with patch("publisher.mqtt_publisher.aiomqtt.Client") as client_cls:
            client_cls.return_value.__aenter__.side_effect = RuntimeError("boom")
            with (
                self.assertLogs("background_tasks", level="ERROR") as logs,
                pytest.raises(RuntimeError, match="boom"),
            ):
                await asyncio.wait_for(publisher.connect(), timeout=2)
        assert "mqtt-loop" in logs.output[0]

    async def test_connection_task_is_the_mqtt_loop_task(self) -> None:
        config = Configuration()
        config.mqtt_host = "localhost"
        config.mqtt_transport_protocol = TransportProtocol.TCP
        publisher = MqttPublisher(config)
        assert publisher.connection_task() is None
        with patch("publisher.mqtt_publisher.aiomqtt.Client") as client_cls:
            client_cls.return_value.__aenter__.side_effect = asyncio.CancelledError
            connect_task = asyncio.get_running_loop().create_task(publisher.connect())
            await asyncio.sleep(0)
            task = publisher.connection_task()
            connect_task.cancel()
            with suppress(asyncio.CancelledError):
                await connect_task
        assert task is not None
        assert task.get_name() == "mqtt-loop"

    def _connected_publisher_with_client(self, client: Any) -> MqttPublisher:
        publisher = MqttPublisher(Configuration())
        publisher.client = client
        publisher._MqttPublisher__connected.set()  # type: ignore[attr-defined]
        return publisher

    async def test_flush_waits_for_in_flight_publishes(self) -> None:
        sent: list[str] = []

        class SlowClient:
            async def publish(self, topic: str, *_: Any, **__: Any) -> None:
                await asyncio.sleep(0.05)
                sent.append(topic)

        publisher = self._connected_publisher_with_client(SlowClient())
        publisher.publish_str("last/words", "bye")
        assert sent == []

        await publisher.flush()

        assert sent == ["saic/last/words"]

    async def test_flush_gives_up_after_timeout(self) -> None:
        release = asyncio.Event()
        sent: list[str] = []

        class StuckClient:
            async def publish(self, topic: str, *_: Any, **__: Any) -> None:
                await release.wait()
                sent.append(topic)

        publisher = self._connected_publisher_with_client(StuckClient())
        publisher.publish_str("stuck", "x")

        with (
            patch("publisher.mqtt_publisher._FLUSH_TIMEOUT", 0.05),
            self.assertLogs("publisher.mqtt_publisher", level="WARNING"),
        ):
            await publisher.flush()
        assert sent == []

        # The publish was not cancelled: it still completes once unblocked
        release.set()
        await publisher.flush()
        assert sent == ["saic/stuck"]

    async def test_flush_without_pending_publishes_returns_immediately(self) -> None:
        await self.mqtt_client.flush()

    async def test_plain_tcp_leaves_tls_insecure_unset(self) -> None:
        """tls_insecure must stay None without TLS, else paho raises ValueError."""
        config = Configuration()
        config.mqtt_host = "localhost"
        config.mqtt_transport_protocol = TransportProtocol.TCP
        kwargs = await self._connect_and_capture_client_kwargs(config)
        assert kwargs["tls_insecure"] is None
        assert kwargs["tls_context"] is None

    async def test_tls_without_hostname_check_enables_tls_insecure(self) -> None:
        config = Configuration()
        config.mqtt_host = "localhost"
        config.mqtt_transport_protocol = TransportProtocol.TLS
        config.tls_server_cert_check_hostname = False
        kwargs = await self._connect_and_capture_client_kwargs(config)
        assert kwargs["tls_insecure"] is True
        assert kwargs["tls_context"] is not None

    async def test_tls_with_hostname_check_leaves_tls_insecure_unset(self) -> None:
        config = Configuration()
        config.mqtt_host = "localhost"
        config.mqtt_transport_protocol = TransportProtocol.TLS
        kwargs = await self._connect_and_capture_client_kwargs(config)
        assert kwargs["tls_insecure"] is None
