from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from saic_ismart_client_ng.exceptions import SaicApiException, SaicLogoutException

from handlers.vehicle_command import VehicleCommandHandler
import mqtt_topics

MQTT_TOPIC = "saic"
VIN = "vin_test_000000000"
VEHICLE_PREFIX = f"vehicles/{VIN}"
CHARGING_SET_TOPIC = f"{MQTT_TOPIC}/{VEHICLE_PREFIX}/{mqtt_topics.DRIVETRAIN_CHARGING_SET}"
CHARGING_RESULT_TOPIC = (
    f"{VEHICLE_PREFIX}/{mqtt_topics.DRIVETRAIN_CHARGING}/{mqtt_topics.RESULT_SUFFIX}"
)
COMMAND_ERROR_TOPIC = f"{VEHICLE_PREFIX}/{mqtt_topics.COMMAND_ERROR}"


def _build(
    *,
    saic_api: AsyncMock | None = None,
    relogin_handler: AsyncMock | None = None,
) -> tuple[VehicleCommandHandler, MagicMock]:
    """Build a VehicleCommandHandler with a MagicMock publisher.

    Returns (handler, mock_publisher) so callers can assert on mock_publisher
    without going through the typed Publisher interface.
    """
    mock_publisher = MagicMock()
    vehicle_state = MagicMock()
    vehicle_state.publisher = mock_publisher
    vehicle_state.vin = VIN
    vehicle_state.get_topic.side_effect = lambda t: f"{VEHICLE_PREFIX}/{t}"
    return (
        VehicleCommandHandler(
            vehicle_state=vehicle_state,
            saic_api=saic_api or AsyncMock(),
            relogin_handler=relogin_handler or AsyncMock(),
            mqtt_topic=MQTT_TOPIC,
            vehicle_prefix=VEHICLE_PREFIX,
        ),
        mock_publisher,
    )


class TestSuccessPath(unittest.IsolatedAsyncioTestCase):
    async def test_successful_command_publishes_success(self) -> None:
        handler, pub = _build()

        await handler.handle_mqtt_command(topic=CHARGING_SET_TOPIC, payload="true")

        pub.publish_str.assert_any_call(CHARGING_RESULT_TOPIC, "Success")
        pub.publish_json.assert_not_called()


class TestNoHandlerFound(unittest.IsolatedAsyncioTestCase):
    async def test_publishes_error_event(self) -> None:
        handler, pub = _build()
        bad_topic = f"{MQTT_TOPIC}/{VEHICLE_PREFIX}/nonexistent/topic/set"
        result_topic = f"{VEHICLE_PREFIX}/nonexistent/topic/{mqtt_topics.RESULT_SUFFIX}"

        await handler.handle_mqtt_command(topic=bad_topic, payload="test")

        pub.publish_str.assert_any_call(
            result_topic,
            "Failed: No handler found for command topic nonexistent/topic/set",
        )
        pub.publish_json.assert_called_once()
        event = pub.publish_json.call_args[0][1]
        assert event["event_type"] == "command_error"
        assert event["command"] == "nonexistent/topic/set"

    async def test_does_not_log_traceback(self) -> None:
        handler, _ = _build()
        bad_topic = f"{MQTT_TOPIC}/{VEHICLE_PREFIX}/nonexistent/topic/set"

        with patch("handlers.vehicle_command.LOG") as mock_log:
            await handler.handle_mqtt_command(topic=bad_topic, payload="test")
            mock_log.error.assert_called_once()
            mock_log.exception.assert_not_called()


class TestMqttGatewayException(unittest.IsolatedAsyncioTestCase):
    async def test_publishes_error_event(self) -> None:
        """An invalid payload triggers MqttGatewayException from payload conversion."""
        handler, pub = _build()

        await handler.handle_mqtt_command(
            topic=CHARGING_SET_TOPIC, payload="not_a_boolean"
        )

        pub.publish_str.assert_any_call(
            CHARGING_RESULT_TOPIC,
            "Failed: Unsupported payload not_a_boolean for command "
            "DrivetrainChargingCommand",
        )
        pub.publish_json.assert_called_once()
        event = pub.publish_json.call_args[0][1]
        assert event["event_type"] == "command_error"
        assert "Unsupported payload" in event["detail"]


class TestSaicApiException(unittest.IsolatedAsyncioTestCase):
    async def test_publishes_error_event(self) -> None:
        saic_api = AsyncMock()
        saic_api.control_charging.side_effect = SaicApiException(
            "operation too frequent", return_code=8
        )
        handler, pub = _build(saic_api=saic_api)

        await handler.handle_mqtt_command(topic=CHARGING_SET_TOPIC, payload="true")

        pub.publish_str.assert_any_call(
            CHARGING_RESULT_TOPIC,
            "Failed: return code: 8, message: operation too frequent",
        )
        pub.publish_json.assert_called_once()
        event = pub.publish_json.call_args[0][1]
        assert event["event_type"] == "command_error"
        assert "operation too frequent" in event["detail"]


class TestUnexpectedException(unittest.IsolatedAsyncioTestCase):
    async def test_uses_safe_detail(self) -> None:
        saic_api = AsyncMock()
        saic_api.control_charging.side_effect = RuntimeError("secret internal detail")
        handler, pub = _build(saic_api=saic_api)

        await handler.handle_mqtt_command(topic=CHARGING_SET_TOPIC, payload="true")

        pub.publish_str.assert_any_call(
            CHARGING_RESULT_TOPIC, "Failed: unexpected error"
        )
        event = pub.publish_json.call_args[0][1]
        assert event["detail"] == "unexpected error"
        assert "secret" not in event["detail"]


class TestSaicLogoutException(unittest.IsolatedAsyncioTestCase):
    async def test_relogin_success_retries_command(self) -> None:
        saic_api = AsyncMock()
        saic_api.control_charging.side_effect = [
            SaicLogoutException("logged out"),
            None,
        ]
        handler, pub = _build(saic_api=saic_api)

        await handler.handle_mqtt_command(topic=CHARGING_SET_TOPIC, payload="true")

        relogin = handler.relogin_handler
        assert isinstance(relogin, AsyncMock)
        relogin.force_login.assert_awaited_once()
        assert saic_api.control_charging.await_count == 2
        pub.publish_str.assert_any_call(CHARGING_RESULT_TOPIC, "Success")
        pub.publish_json.assert_not_called()

    async def test_relogin_failure_publishes_error_event(self) -> None:
        saic_api = AsyncMock()
        saic_api.control_charging.side_effect = SaicLogoutException("logged out")
        relogin = AsyncMock()
        relogin.force_login.side_effect = Exception("login failed")
        handler, pub = _build(saic_api=saic_api, relogin_handler=relogin)

        await handler.handle_mqtt_command(topic=CHARGING_SET_TOPIC, payload="true")

        pub.publish_str.assert_any_call(
            CHARGING_RESULT_TOPIC, "Failed: relogin failed (login failed)"
        )
        pub.publish_json.assert_called_once()
        event = pub.publish_json.call_args[0][1]
        assert "relogin failed" in event["detail"]

    async def test_retry_failure_publishes_error_event(self) -> None:
        saic_api = AsyncMock()
        saic_api.control_charging.side_effect = [
            SaicLogoutException("logged out"),
            RuntimeError("retry boom"),
        ]
        handler, pub = _build(saic_api=saic_api)

        await handler.handle_mqtt_command(topic=CHARGING_SET_TOPIC, payload="true")

        pub.publish_str.assert_any_call(
            CHARGING_RESULT_TOPIC, "Failed: retry boom"
        )
        pub.publish_json.assert_called_once()
        event = pub.publish_json.call_args[0][1]
        assert event["detail"] == "retry boom"


class TestReportFailureResilience(unittest.IsolatedAsyncioTestCase):
    async def test_publish_str_failure_does_not_prevent_error_event(self) -> None:
        saic_api = AsyncMock()
        saic_api.control_charging.side_effect = SaicApiException("err", return_code=1)
        handler, pub = _build(saic_api=saic_api)
        pub.publish_str.side_effect = ConnectionError("broker down")

        await handler.handle_mqtt_command(topic=CHARGING_SET_TOPIC, payload="true")

        pub.publish_json.assert_called_once()
        event = pub.publish_json.call_args[0][1]
        assert event["event_type"] == "command_error"

    async def test_publish_json_failure_does_not_raise(self) -> None:
        saic_api = AsyncMock()
        saic_api.control_charging.side_effect = SaicApiException("err", return_code=1)
        handler, pub = _build(saic_api=saic_api)
        pub.publish_json.side_effect = ConnectionError("broker down")

        await handler.handle_mqtt_command(topic=CHARGING_SET_TOPIC, payload="true")

        pub.publish_str.assert_called_once()


class TestErrorEventPayload(unittest.IsolatedAsyncioTestCase):
    async def test_topic_uses_vehicle_prefix(self) -> None:
        saic_api = AsyncMock()
        saic_api.control_charging.side_effect = SaicApiException("err", return_code=1)
        handler, pub = _build(saic_api=saic_api)

        await handler.handle_mqtt_command(topic=CHARGING_SET_TOPIC, payload="true")

        error_topic = pub.publish_json.call_args[0][0]
        assert error_topic == COMMAND_ERROR_TOPIC

    async def test_payload_structure(self) -> None:
        saic_api = AsyncMock()
        saic_api.control_charging.side_effect = SaicApiException(
            "operation too frequent", return_code=8
        )
        handler, pub = _build(saic_api=saic_api)

        await handler.handle_mqtt_command(topic=CHARGING_SET_TOPIC, payload="true")

        event = pub.publish_json.call_args[0][1]
        assert set(event.keys()) == {"event_type", "command", "detail"}
        assert event["event_type"] == "command_error"
        assert event["command"] == mqtt_topics.DRIVETRAIN_CHARGING_SET
        assert "operation too frequent" in event["detail"]
