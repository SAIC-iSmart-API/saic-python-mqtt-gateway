from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from saic_ismart_client_ng.exceptions import SaicApiException, SaicLogoutException

from exceptions import MqttGatewayException
from handlers.command.base import RESULT_REFRESH_AND_CLEAR
from handlers.vehicle_command import VehicleCommandHandler
import mqtt_topics

MQTT_TOPIC = "saic"
VIN = "vin_test_000000000"
VEHICLE_PREFIX = f"vehicles/{VIN}"


def _make_handler(
    *,
    vehicle_state: MagicMock | None = None,
    saic_api: AsyncMock | None = None,
    relogin_handler: AsyncMock | None = None,
) -> VehicleCommandHandler:
    if vehicle_state is None:
        vehicle_state = MagicMock()
        vehicle_state.publisher = MagicMock()
        vehicle_state.get_topic.side_effect = lambda t: f"{VEHICLE_PREFIX}/{t}"
    if saic_api is None:
        saic_api = AsyncMock()
    if relogin_handler is None:
        relogin_handler = AsyncMock()
    return VehicleCommandHandler(
        vehicle_state=vehicle_state,
        saic_api=saic_api,
        relogin_handler=relogin_handler,
        mqtt_topic=MQTT_TOPIC,
        vehicle_prefix=VEHICLE_PREFIX,
    )


def _command_topic(command_topic_suffix: str) -> str:
    return f"{MQTT_TOPIC}/{VEHICLE_PREFIX}/{command_topic_suffix}"


def _result_topic(command_topic_suffix: str) -> str:
    base = command_topic_suffix.removesuffix(mqtt_topics.SET_SUFFIX).removesuffix("/")
    return f"{VEHICLE_PREFIX}/{base}/{mqtt_topics.RESULT_SUFFIX}"


class TestVehicleCommandSuccess(unittest.IsolatedAsyncioTestCase):
    async def test_successful_command_publishes_success(self) -> None:
        handler = _make_handler()
        topic = _command_topic(mqtt_topics.DRIVETRAIN_CHARGING_SET)
        result_topic = _result_topic(mqtt_topics.DRIVETRAIN_CHARGING_SET)

        await handler.handle_mqtt_command(topic=topic, payload="true")

        handler.publisher.publish_str.assert_any_call(result_topic, "Success")
        handler.publisher.publish_json.assert_not_called()


class TestVehicleCommandNoHandler(unittest.IsolatedAsyncioTestCase):
    async def test_no_handler_publishes_error_event(self) -> None:
        handler = _make_handler()
        topic = _command_topic("nonexistent/topic/set")
        result_topic = _result_topic("nonexistent/topic/set")

        await handler.handle_mqtt_command(topic=topic, payload="test")

        handler.publisher.publish_str.assert_called_once_with(
            result_topic,
            "Failed: No handler found for command topic nonexistent/topic/set",
        )
        handler.publisher.publish_json.assert_called_once()
        event_payload = handler.publisher.publish_json.call_args[0][1]
        assert event_payload["event_type"] == "command_error"
        assert event_payload["command"] == "nonexistent/topic/set"

    async def test_no_handler_does_not_log_traceback(self) -> None:
        handler = _make_handler()
        topic = _command_topic("nonexistent/topic/set")

        with patch("handlers.vehicle_command.LOG") as mock_log:
            await handler.handle_mqtt_command(topic=topic, payload="test")
            mock_log.error.assert_called_once()
            mock_log.exception.assert_not_called()


class TestVehicleCommandMqttGatewayException(unittest.IsolatedAsyncioTestCase):
    async def test_mqtt_gateway_exception_publishes_error_event(self) -> None:
        handler = _make_handler()
        topic = _command_topic(mqtt_topics.DRIVETRAIN_CHARGING_SET)
        result_topic = _result_topic(mqtt_topics.DRIVETRAIN_CHARGING_SET)

        cmd_handler = handler._VehicleCommandHandler__command_handlers[
            mqtt_topics.DRIVETRAIN_CHARGING_SET
        ]
        cmd_handler.handle = AsyncMock(
            side_effect=MqttGatewayException("test error")
        )

        await handler.handle_mqtt_command(topic=topic, payload="true")

        handler.publisher.publish_str.assert_called_once_with(
            result_topic, "Failed: test error"
        )
        handler.publisher.publish_json.assert_called_once()
        event_payload = handler.publisher.publish_json.call_args[0][1]
        assert event_payload["event_type"] == "command_error"
        assert event_payload["detail"] == "test error"


class TestVehicleCommandSaicApiException(unittest.IsolatedAsyncioTestCase):
    async def test_saic_api_exception_publishes_error_event(self) -> None:
        handler = _make_handler()
        topic = _command_topic(mqtt_topics.DRIVETRAIN_CHARGING_SET)
        result_topic = _result_topic(mqtt_topics.DRIVETRAIN_CHARGING_SET)

        cmd_handler = handler._VehicleCommandHandler__command_handlers[
            mqtt_topics.DRIVETRAIN_CHARGING_SET
        ]
        cmd_handler.handle = AsyncMock(
            side_effect=SaicApiException("api error", return_code=8)
        )

        await handler.handle_mqtt_command(topic=topic, payload="true")

        handler.publisher.publish_str.assert_called_once_with(
            result_topic, "Failed: return code: 8, message: api error"
        )
        handler.publisher.publish_json.assert_called_once()
        event_payload = handler.publisher.publish_json.call_args[0][1]
        assert event_payload["detail"] == "return code: 8, message: api error"


class TestVehicleCommandUnexpectedException(unittest.IsolatedAsyncioTestCase):
    async def test_unexpected_exception_uses_safe_detail(self) -> None:
        handler = _make_handler()
        topic = _command_topic(mqtt_topics.DRIVETRAIN_CHARGING_SET)
        result_topic = _result_topic(mqtt_topics.DRIVETRAIN_CHARGING_SET)

        cmd_handler = handler._VehicleCommandHandler__command_handlers[
            mqtt_topics.DRIVETRAIN_CHARGING_SET
        ]
        cmd_handler.handle = AsyncMock(
            side_effect=RuntimeError("secret internal detail")
        )

        await handler.handle_mqtt_command(topic=topic, payload="true")

        handler.publisher.publish_str.assert_called_once_with(
            result_topic, "Failed: unexpected error"
        )
        event_payload = handler.publisher.publish_json.call_args[0][1]
        assert event_payload["detail"] == "unexpected error"
        assert "secret" not in event_payload["detail"]


class TestVehicleCommandSaicLogoutException(unittest.IsolatedAsyncioTestCase):
    async def test_logout_relogin_success_retries_command(self) -> None:
        handler = _make_handler()
        topic = _command_topic(mqtt_topics.DRIVETRAIN_CHARGING_SET)
        result_topic = _result_topic(mqtt_topics.DRIVETRAIN_CHARGING_SET)

        cmd_handler = handler._VehicleCommandHandler__command_handlers[
            mqtt_topics.DRIVETRAIN_CHARGING_SET
        ]
        cmd_handler.handle = AsyncMock(
            side_effect=[SaicLogoutException("logged out"), RESULT_REFRESH_AND_CLEAR]
        )

        await handler.handle_mqtt_command(topic=topic, payload="true")

        handler.relogin_handler.force_login.assert_awaited_once()
        assert cmd_handler.handle.await_count == 2
        handler.publisher.publish_str.assert_any_call(result_topic, "Success")
        handler.publisher.publish_json.assert_not_called()

    async def test_logout_relogin_failure_publishes_error_event(self) -> None:
        handler = _make_handler()
        topic = _command_topic(mqtt_topics.DRIVETRAIN_CHARGING_SET)
        result_topic = _result_topic(mqtt_topics.DRIVETRAIN_CHARGING_SET)

        cmd_handler = handler._VehicleCommandHandler__command_handlers[
            mqtt_topics.DRIVETRAIN_CHARGING_SET
        ]
        cmd_handler.handle = AsyncMock(side_effect=SaicLogoutException("logged out"))
        handler.relogin_handler.force_login = AsyncMock(
            side_effect=Exception("login failed")
        )

        await handler.handle_mqtt_command(topic=topic, payload="true")

        handler.publisher.publish_str.assert_called_once_with(
            result_topic, "Failed: relogin failed (login failed)"
        )
        handler.publisher.publish_json.assert_called_once()
        event_payload = handler.publisher.publish_json.call_args[0][1]
        assert "relogin failed" in event_payload["detail"]

    async def test_logout_retry_failure_publishes_error_event(self) -> None:
        handler = _make_handler()
        topic = _command_topic(mqtt_topics.DRIVETRAIN_CHARGING_SET)
        result_topic = _result_topic(mqtt_topics.DRIVETRAIN_CHARGING_SET)

        cmd_handler = handler._VehicleCommandHandler__command_handlers[
            mqtt_topics.DRIVETRAIN_CHARGING_SET
        ]
        cmd_handler.handle = AsyncMock(
            side_effect=[SaicLogoutException("logged out"), RuntimeError("retry boom")]
        )

        await handler.handle_mqtt_command(topic=topic, payload="true")

        handler.publisher.publish_str.assert_called_once_with(
            result_topic, "Failed: retry boom"
        )
        handler.publisher.publish_json.assert_called_once()
        event_payload = handler.publisher.publish_json.call_args[0][1]
        assert event_payload["detail"] == "retry boom"


class TestReportCommandFailureResilience(unittest.IsolatedAsyncioTestCase):
    async def test_publish_str_failure_does_not_prevent_error_event(self) -> None:
        handler = _make_handler()
        topic = _command_topic(mqtt_topics.DRIVETRAIN_CHARGING_SET)

        cmd_handler = handler._VehicleCommandHandler__command_handlers[
            mqtt_topics.DRIVETRAIN_CHARGING_SET
        ]
        cmd_handler.handle = AsyncMock(
            side_effect=MqttGatewayException("cmd error")
        )
        handler.publisher.publish_str.side_effect = ConnectionError("broker down")

        await handler.handle_mqtt_command(topic=topic, payload="true")

        handler.publisher.publish_json.assert_called_once()
        event_payload = handler.publisher.publish_json.call_args[0][1]
        assert event_payload["detail"] == "cmd error"

    async def test_publish_json_failure_does_not_raise(self) -> None:
        handler = _make_handler()
        topic = _command_topic(mqtt_topics.DRIVETRAIN_CHARGING_SET)

        cmd_handler = handler._VehicleCommandHandler__command_handlers[
            mqtt_topics.DRIVETRAIN_CHARGING_SET
        ]
        cmd_handler.handle = AsyncMock(
            side_effect=MqttGatewayException("cmd error")
        )
        handler.publisher.publish_json.side_effect = ConnectionError("broker down")

        await handler.handle_mqtt_command(topic=topic, payload="true")

        handler.publisher.publish_str.assert_called_once()


class TestCommandErrorEventPayload(unittest.IsolatedAsyncioTestCase):
    async def test_error_event_topic_uses_vehicle_prefix(self) -> None:
        handler = _make_handler()
        topic = _command_topic(mqtt_topics.DRIVETRAIN_CHARGING_SET)

        cmd_handler = handler._VehicleCommandHandler__command_handlers[
            mqtt_topics.DRIVETRAIN_CHARGING_SET
        ]
        cmd_handler.handle = AsyncMock(
            side_effect=MqttGatewayException("some error")
        )

        await handler.handle_mqtt_command(topic=topic, payload="true")

        error_topic = handler.publisher.publish_json.call_args[0][0]
        assert error_topic == f"{VEHICLE_PREFIX}/{mqtt_topics.COMMAND_ERROR}"

    async def test_error_event_payload_structure(self) -> None:
        handler = _make_handler()
        topic = _command_topic(mqtt_topics.DRIVETRAIN_CHARGING_SET)

        cmd_handler = handler._VehicleCommandHandler__command_handlers[
            mqtt_topics.DRIVETRAIN_CHARGING_SET
        ]
        cmd_handler.handle = AsyncMock(
            side_effect=SaicApiException("operation too frequent", return_code=8)
        )

        await handler.handle_mqtt_command(topic=topic, payload="true")

        event_payload = handler.publisher.publish_json.call_args[0][1]
        assert set(event_payload.keys()) == {"event_type", "command", "detail"}
        assert event_payload["event_type"] == "command_error"
        assert event_payload["command"] == mqtt_topics.DRIVETRAIN_CHARGING_SET
        assert event_payload["detail"] == "return code: 8, message: operation too frequent"
