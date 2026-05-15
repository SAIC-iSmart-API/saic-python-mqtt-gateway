from __future__ import annotations

import datetime
import json
from typing import cast
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from saic_ismart_client_ng.api.vehicle.schema import VehicleModelConfiguration, VinInfo
from saic_ismart_client_ng.api.vehicle_charging import (
    ChargeCurrentLimitCode,
    ScheduledChargingMode,
    TargetBatteryCode,
)
from saic_ismart_client_ng.exceptions import SaicApiException, SaicLogoutException

from handlers.vehicle_command import VehicleCommandHandler
import mqtt_topics
from status_publisher.charge.chrg_mgmt_data import ScheduledCharging
from vehicle import RefreshMode
from vehicle_info import VehicleInfo

MQTT_TOPIC = "saic"
VIN = "vin_test_000000000"
VEHICLE_PREFIX = f"vehicles/{VIN}"
CHARGING_SET_TOPIC = (
    f"{MQTT_TOPIC}/{VEHICLE_PREFIX}/{mqtt_topics.DRIVETRAIN_CHARGING_SET}"
)
CHARGING_RESULT_TOPIC = (
    f"{VEHICLE_PREFIX}/{mqtt_topics.DRIVETRAIN_CHARGING}/{mqtt_topics.RESULT_SUFFIX}"
)
COMMAND_ERROR_TOPIC = f"{VEHICLE_PREFIX}/{mqtt_topics.COMMAND_ERROR}"
SOC_TARGET_SET_TOPIC = (
    f"{MQTT_TOPIC}/{VEHICLE_PREFIX}/{mqtt_topics.DRIVETRAIN_SOC_TARGET_SET}"
)
SOC_TARGET_STATE_TOPIC = f"{VEHICLE_PREFIX}/{mqtt_topics.DRIVETRAIN_SOC_TARGET}"
SOC_TARGET_RESULT_TOPIC = (
    f"{VEHICLE_PREFIX}/{mqtt_topics.DRIVETRAIN_SOC_TARGET}/{mqtt_topics.RESULT_SUFFIX}"
)
CHARGECURRENT_SET_TOPIC = (
    f"{MQTT_TOPIC}/{VEHICLE_PREFIX}/{mqtt_topics.DRIVETRAIN_CHARGECURRENT_LIMIT_SET}"
)
CHARGECURRENT_STATE_TOPIC = (
    f"{VEHICLE_PREFIX}/{mqtt_topics.DRIVETRAIN_CHARGECURRENT_LIMIT}"
)
CHARGING_SCHEDULE_SET_TOPIC = (
    f"{MQTT_TOPIC}/{VEHICLE_PREFIX}/{mqtt_topics.DRIVETRAIN_CHARGING_SCHEDULE_SET}"
)
CHARGING_SCHEDULE_STATE_TOPIC = (
    f"{VEHICLE_PREFIX}/{mqtt_topics.DRIVETRAIN_CHARGING_SCHEDULE}"
)
BATTERY_HEATING_SET_TOPIC = f"{MQTT_TOPIC}/{VEHICLE_PREFIX}/{mqtt_topics.DRIVETRAIN_BATTERY_HEATING_SCHEDULE_SET}"
BATTERY_HEATING_STATE_TOPIC = (
    f"{VEHICLE_PREFIX}/{mqtt_topics.DRIVETRAIN_BATTERY_HEATING_SCHEDULE}"
)


def _build(
    *,
    saic_api: AsyncMock | None = None,
    relogin_handler: AsyncMock | None = None,
    vehicle_state: MagicMock | None = None,
) -> tuple[VehicleCommandHandler, MagicMock]:
    """Build a VehicleCommandHandler with a MagicMock publisher.

    Returns (handler, mock_publisher) so callers can assert on mock_publisher
    without going through the typed Publisher interface.
    """
    mock_publisher = MagicMock()
    if vehicle_state is None:
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


def _make_target_soc_state(
    *, current: TargetBatteryCode | None = TargetBatteryCode.P_80
) -> MagicMock:
    """Build a vehicle state mock that supports target SoC.

    Reports `current` as the previously applied value (for rollback testing).
    """
    vin_info = VinInfo()
    vin_info.vin = VIN
    vin_info.vehicleModelConfiguration = [
        VehicleModelConfiguration(itemCode="BType", itemValue="1"),
    ]
    vehicle_info = VehicleInfo(vin_info, None)

    state = MagicMock()
    state.vehicle = vehicle_info
    state.target_soc = current
    return state


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

        pub.publish_str.assert_any_call(CHARGING_RESULT_TOPIC, "Failed: retry boom")
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


class TestEagerStatePublish(unittest.IsolatedAsyncioTestCase):
    """Verify the dispatcher's eager-publish + rollback path.

    With `optimistic: false`, HA waits for `state_topic` before updating the
    slider. The dispatcher must therefore publish the expected state on
    receipt (instant UX feedback) and revert to the prior value if the SAIC
    call fails (visible rejection).
    """

    async def test_publishes_expected_state_on_receipt(self) -> None:
        state = _make_target_soc_state(current=TargetBatteryCode.P_80)
        handler, pub = _build(vehicle_state=state)

        await handler.handle_mqtt_command(topic=SOC_TARGET_SET_TOPIC, payload="90")

        pub.publish.assert_any_call(SOC_TARGET_STATE_TOPIC, 90)

    async def test_rollback_on_saic_api_failure(self) -> None:
        saic_api = AsyncMock()
        saic_api.set_target_battery_soc.side_effect = SaicApiException(
            "rejected", return_code=4
        )
        state = _make_target_soc_state(current=TargetBatteryCode.P_80)
        handler, pub = _build(saic_api=saic_api, vehicle_state=state)

        await handler.handle_mqtt_command(topic=SOC_TARGET_SET_TOPIC, payload="90")

        # First the expected state for the requested value (90), then the
        # rollback to the captured prior value (80).
        state_publishes = [
            call.args[1]
            for call in pub.publish.call_args_list
            if call.args[0] == SOC_TARGET_STATE_TOPIC
        ]
        assert state_publishes == [90, 80]

    async def test_no_rollback_when_no_prior_state_captured(self) -> None:
        # If the gateway has not yet learned the vehicle's current target SoC
        # there is nothing to roll back to, so we must not publish None.
        saic_api = AsyncMock()
        saic_api.set_target_battery_soc.side_effect = SaicApiException(
            "rejected", return_code=4
        )
        state = _make_target_soc_state(current=None)
        handler, pub = _build(saic_api=saic_api, vehicle_state=state)

        await handler.handle_mqtt_command(topic=SOC_TARGET_SET_TOPIC, payload="90")

        state_publishes = [
            call.args[1]
            for call in pub.publish.call_args_list
            if call.args[0] == SOC_TARGET_STATE_TOPIC
        ]
        assert state_publishes == [90]

    async def test_non_numeric_payload_skips_publish(self) -> None:
        state = _make_target_soc_state(current=TargetBatteryCode.P_80)
        handler, pub = _build(vehicle_state=state)

        await handler.handle_mqtt_command(
            topic=SOC_TARGET_SET_TOPIC, payload="not_a_number"
        )

        state_publishes = [
            call.args
            for call in pub.publish.call_args_list
            if call.args[0] == SOC_TARGET_STATE_TOPIC
        ]
        assert state_publishes == []

    async def test_numeric_but_unsupported_bucket_skips_publish(self) -> None:
        # 85% is numeric but not one of the discrete TargetBatteryCode buckets
        # (40/50/60/70/80/90/100). `from_percentage` raises, expected_state
        # returns None, and nothing is published to state_topic.
        state = _make_target_soc_state(current=TargetBatteryCode.P_80)
        handler, pub = _build(vehicle_state=state)

        await handler.handle_mqtt_command(topic=SOC_TARGET_SET_TOPIC, payload="85")

        state_publishes = [
            call.args
            for call in pub.publish.call_args_list
            if call.args[0] == SOC_TARGET_STATE_TOPIC
        ]
        assert state_publishes == []

    async def test_switch_command_does_not_publish_state(self) -> None:
        # Switches don't override state_topic on CommandHandlerBase, so it
        # stays None and the dispatcher skips the eager-publish path. Verify
        # nothing leaks to a state topic.
        handler, pub = _build()

        await handler.handle_mqtt_command(topic=CHARGING_SET_TOPIC, payload="true")

        for call in pub.publish.call_args_list:
            assert "drivetrain/charging" not in call.args[0] or "/set" in call.args[0]

    async def test_retained_soc_target_does_not_leak_to_state_topic(self) -> None:
        # SoC target has not opted into is_replayable_when_retained(), so a
        # retained `/set` (e.g. from a misbehaving non-HA client that retained
        # the topic) is dropped at the dispatcher gate before the eager-publish
        # block runs. Nothing must leak to state_topic — otherwise the slider
        # would jump on reconnect to a value the SAIC API never confirmed.
        state = _make_target_soc_state(current=TargetBatteryCode.P_80)
        handler, pub = _build(vehicle_state=state)

        await handler.handle_mqtt_command(
            topic=SOC_TARGET_SET_TOPIC, payload="90", retained=True
        )

        state_publishes = [
            call.args[1]
            for call in pub.publish.call_args_list
            if call.args[0] == SOC_TARGET_STATE_TOPIC
        ]
        assert state_publishes == []


class TestEagerStatePublishOtherEntities(unittest.IsolatedAsyncioTestCase):
    """Eager-publish + rollback for the other API-backed writable entities.

    Same contract as the SoC slider: charge current limit (string state) and
    the two schedule entities (JSON-dict state) all need eager-echo because
    HA's `optimistic: false` would otherwise leave the user staring at a
    frozen control while the SAIC roundtrip completes.
    """

    async def test_chargecurrent_limit_echo_and_rollback(self) -> None:
        saic_api = AsyncMock()
        saic_api.set_target_battery_soc.side_effect = SaicApiException(
            "rejected", return_code=4
        )
        state = MagicMock()
        state.charge_current_limit = ChargeCurrentLimitCode.C_6A
        state.target_soc = TargetBatteryCode.P_80
        handler, pub = _build(saic_api=saic_api, vehicle_state=state)

        await handler.handle_mqtt_command(topic=CHARGECURRENT_SET_TOPIC, payload="MAX")

        state_publishes = [
            call.args[1]
            for call in pub.publish.call_args_list
            if call.args[0] == CHARGECURRENT_STATE_TOPIC
        ]
        assert state_publishes == [
            ChargeCurrentLimitCode.C_MAX.limit,
            ChargeCurrentLimitCode.C_6A.limit,
        ]

    async def test_charging_schedule_echo_and_rollback(self) -> None:
        saic_api = AsyncMock()
        saic_api.set_schedule_charging.side_effect = SaicApiException(
            "rejected", return_code=4
        )
        prior = ScheduledCharging(
            start_time=datetime.time(7, 0),
            end_time=datetime.time(9, 0),
            mode=ScheduledChargingMode.DISABLED,
        )
        state = _make_target_soc_state(current=TargetBatteryCode.P_80)
        state.scheduled_charging = prior
        handler, pub = _build(saic_api=saic_api, vehicle_state=state)

        payload = json.dumps(
            {"startTime": "08:00", "endTime": "10:00", "mode": "UNTIL_CONFIGURED_TIME"}
        )
        await handler.handle_mqtt_command(
            topic=CHARGING_SCHEDULE_SET_TOPIC, payload=payload
        )

        state_publishes = [
            call.args[1]
            for call in pub.publish.call_args_list
            if call.args[0] == CHARGING_SCHEDULE_STATE_TOPIC
        ]
        assert state_publishes == [
            {
                "startTime": "08:00",
                "endTime": "10:00",
                "mode": "UNTIL_CONFIGURED_TIME",
            },
            {"startTime": "07:00", "endTime": "09:00", "mode": "DISABLED"},
        ]

    async def test_battery_heating_schedule_echo_and_rollback(self) -> None:
        saic_api = AsyncMock()
        saic_api.enable_schedule_battery_heating.side_effect = SaicApiException(
            "rejected", return_code=4
        )
        state = MagicMock()
        state.scheduled_battery_heating_start = datetime.time(6, 30)
        state.scheduled_battery_heating_enabled = True
        state.user_timezone = None
        handler, pub = _build(saic_api=saic_api, vehicle_state=state)

        payload = json.dumps({"startTime": "08:00", "mode": "ON"})
        await handler.handle_mqtt_command(
            topic=BATTERY_HEATING_SET_TOPIC, payload=payload
        )

        state_publishes = [
            call.args[1]
            for call in pub.publish.call_args_list
            if call.args[0] == BATTERY_HEATING_STATE_TOPIC
        ]
        assert state_publishes == [
            {"startTime": "08:00", "mode": "on"},
            {"startTime": "06:30", "mode": "on"},
        ]
        # The fix moves the in-memory mutation to after API success. With the
        # API call failing, update_scheduled_battery_heating must NOT have run
        # — otherwise the gateway holds the failed-new value and the next
        # eager-echo's `current_state` would be wrong.
        state.update_scheduled_battery_heating.assert_not_called()


class TestEagerStateEdgeCases(unittest.IsolatedAsyncioTestCase):
    """Edge cases around the eager-echo path that aren't tied to a single entity."""

    async def test_result_do_nothing_rolls_back_eager_echo(self) -> None:
        # Vehicle without target-SoC support: the SoC handler returns
        # RESULT_DO_NOTHING after we've already echoed the requested value.
        # Without the fix the slider would stick on the unsupported value.
        vin_info = VinInfo()
        vin_info.vin = VIN
        vin_info.vehicleModelConfiguration = []
        state = MagicMock()
        state.vehicle = VehicleInfo(vin_info, None)
        state.target_soc = TargetBatteryCode.P_80
        handler, pub = _build(vehicle_state=state)

        await handler.handle_mqtt_command(topic=SOC_TARGET_SET_TOPIC, payload="90")

        state_publishes = [
            call.args[1]
            for call in pub.publish.call_args_list
            if call.args[0] == SOC_TARGET_STATE_TOPIC
        ]
        assert state_publishes == [90, 80]

    async def test_logout_retry_success_preserves_eager_echo(self) -> None:
        # First SAIC call hits a logout, retry after relogin succeeds. The
        # eager-echoed value must remain on the broker (no spurious rollback).
        saic_api = AsyncMock()
        saic_api.set_target_battery_soc.side_effect = [
            SaicLogoutException("logged out"),
            None,
        ]
        state = _make_target_soc_state(current=TargetBatteryCode.P_80)
        handler, pub = _build(saic_api=saic_api, vehicle_state=state)

        await handler.handle_mqtt_command(topic=SOC_TARGET_SET_TOPIC, payload="90")

        state_publishes = [
            call.args[1]
            for call in pub.publish.call_args_list
            if call.args[0] == SOC_TARGET_STATE_TOPIC
        ]
        # Only the eager echo — no rollback on the successful retry.
        assert state_publishes == [90]
        assert saic_api.set_target_battery_soc.await_count == 2
        pub.publish_str.assert_any_call(SOC_TARGET_RESULT_TOPIC, "Success")

    async def test_broker_failure_during_rollback_does_not_crash(self) -> None:
        # The broker drops while we try to roll back the eager echo. The
        # dispatcher must still attempt the rollback and publish the failure
        # to the result topic, not propagate the publish exception.
        saic_api = AsyncMock()
        saic_api.set_target_battery_soc.side_effect = SaicApiException(
            "rejected", return_code=4
        )
        state = _make_target_soc_state(current=TargetBatteryCode.P_80)
        handler, pub = _build(saic_api=saic_api, vehicle_state=state)
        # First publish is the eager echo (succeeds), second is the rollback
        # (broker is now down).
        pub.publish.side_effect = [None, ConnectionError("broker down")]

        await handler.handle_mqtt_command(topic=SOC_TARGET_SET_TOPIC, payload="90")

        # Both publish calls to the state topic must fire: the rollback was
        # attempted even though the broker raised on it.
        state_publishes = [
            call.args
            for call in pub.publish.call_args_list
            if call.args[0] == SOC_TARGET_STATE_TOPIC
        ]
        assert len(state_publishes) == 2
        # And the dispatcher kept going to publish the failure result.
        result_calls = [
            call.args
            for call in pub.publish_str.call_args_list
            if call.args[0] == SOC_TARGET_RESULT_TOPIC
        ]
        assert any("Failed:" in args[1] for args in result_calls)

    async def test_malformed_charging_schedule_skips_eager_echo(self) -> None:
        # Bad JSON in the payload: convert_payload (and thus expected_state)
        # raises and the dispatcher must skip the eager publish entirely.
        prior = ScheduledCharging(
            start_time=datetime.time(7, 0),
            end_time=datetime.time(9, 0),
            mode=ScheduledChargingMode.DISABLED,
        )
        state = _make_target_soc_state(current=TargetBatteryCode.P_80)
        state.scheduled_charging = prior
        handler, pub = _build(vehicle_state=state)

        await handler.handle_mqtt_command(
            topic=CHARGING_SCHEDULE_SET_TOPIC, payload="not json {"
        )

        state_publishes = [
            call.args
            for call in pub.publish.call_args_list
            if call.args[0] == CHARGING_SCHEDULE_STATE_TOPIC
        ]
        assert state_publishes == []


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


REFRESH_MODE_SET_TOPIC = f"{MQTT_TOPIC}/{VEHICLE_PREFIX}/{mqtt_topics.REFRESH_MODE_SET}"
REFRESH_MODE_RESULT_TOPIC = (
    f"{VEHICLE_PREFIX}/{mqtt_topics.REFRESH_MODE}/{mqtt_topics.RESULT_SUFFIX}"
)
TOTAL_BATTERY_CAPACITY_SET_TOPIC = (
    f"{MQTT_TOPIC}/{VEHICLE_PREFIX}/{mqtt_topics.DRIVETRAIN_TOTAL_BATTERY_CAPACITY_SET}"
)
TOTAL_BATTERY_CAPACITY_RESULT_TOPIC = (
    f"{VEHICLE_PREFIX}/{mqtt_topics.DRIVETRAIN_TOTAL_BATTERY_CAPACITY}"
    f"/{mqtt_topics.RESULT_SUFFIX}"
)
TOTAL_BATTERY_CAPACITY_STATE_TOPIC = (
    f"{VEHICLE_PREFIX}/{mqtt_topics.DRIVETRAIN_TOTAL_BATTERY_CAPACITY}"
)


class TestRetainedReplay(unittest.IsolatedAsyncioTestCase):
    """Behavior for retained `/set` commands replayed on broker reconnect.

    Idempotent values (refresh periods, OFF/PERIODIC mode, battery capacity)
    must seed in-memory state. One-shot refresh modes (FORCE /
    CHARGING_DETECTION) must be dropped to avoid looping a poll on every
    gateway restart.
    """

    async def test_retained_force_refresh_mode_dropped(self) -> None:
        handler, pub = _build()
        vehicle_state = cast("MagicMock", handler.vehicle_state)

        await handler.handle_mqtt_command(
            topic=REFRESH_MODE_SET_TOPIC, payload="force", retained=True
        )

        vehicle_state.set_refresh_mode.assert_not_called()
        pub.publish_str.assert_any_call(REFRESH_MODE_RESULT_TOPIC, "Success")

    async def test_retained_charging_detection_refresh_mode_dropped(self) -> None:
        handler, pub = _build()
        vehicle_state = cast("MagicMock", handler.vehicle_state)

        await handler.handle_mqtt_command(
            topic=REFRESH_MODE_SET_TOPIC,
            payload="charging_detection",
            retained=True,
        )

        vehicle_state.set_refresh_mode.assert_not_called()
        pub.publish_str.assert_any_call(REFRESH_MODE_RESULT_TOPIC, "Success")

    async def test_retained_periodic_refresh_mode_applied(self) -> None:
        handler, _pub = _build()
        vehicle_state = cast("MagicMock", handler.vehicle_state)

        await handler.handle_mqtt_command(
            topic=REFRESH_MODE_SET_TOPIC, payload="periodic", retained=True
        )

        vehicle_state.set_refresh_mode.assert_called_once()
        mode_arg = vehicle_state.set_refresh_mode.call_args[0][0]
        assert mode_arg is RefreshMode.PERIODIC

    async def test_retained_off_refresh_mode_applied(self) -> None:
        handler, _pub = _build()
        vehicle_state = cast("MagicMock", handler.vehicle_state)

        await handler.handle_mqtt_command(
            topic=REFRESH_MODE_SET_TOPIC, payload="off", retained=True
        )

        vehicle_state.set_refresh_mode.assert_called_once()
        mode_arg = vehicle_state.set_refresh_mode.call_args[0][0]
        assert mode_arg is RefreshMode.OFF

    async def test_non_retained_force_still_applied(self) -> None:
        handler, _pub = _build()
        vehicle_state = cast("MagicMock", handler.vehicle_state)

        await handler.handle_mqtt_command(
            topic=REFRESH_MODE_SET_TOPIC, payload="force", retained=False
        )

        vehicle_state.set_refresh_mode.assert_called_once()
        mode_arg = vehicle_state.set_refresh_mode.call_args[0][0]
        assert mode_arg is RefreshMode.FORCE

    async def test_retained_battery_capacity_replays_to_vehicle_info(self) -> None:
        handler, pub = _build()
        vehicle_state = cast("MagicMock", handler.vehicle_state)
        vehicle_state.vehicle.real_battery_capacity = 50.0

        await handler.handle_mqtt_command(
            topic=TOTAL_BATTERY_CAPACITY_SET_TOPIC, payload="50.0", retained=True
        )

        vehicle_state.update_battery_capacity.assert_called_once_with(50.0)
        pub.publish_float.assert_any_call(TOTAL_BATTERY_CAPACITY_STATE_TOPIC, 50.0)
        pub.publish_str.assert_any_call(TOTAL_BATTERY_CAPACITY_RESULT_TOPIC, "Success")

    async def test_battery_capacity_zero_payload_publishes_model_default(self) -> None:
        """Payload `0` clears the override; the per-model default is republished."""
        handler, pub = _build()
        vehicle_state = cast("MagicMock", handler.vehicle_state)
        # update_battery_capacity(0) clears the override; real_battery_capacity then
        # falls back to the per-model default (e.g. 64 kWh for an MG4 NMC).
        vehicle_state.vehicle.real_battery_capacity = 64.0

        await handler.handle_mqtt_command(
            topic=TOTAL_BATTERY_CAPACITY_SET_TOPIC, payload="0", retained=False
        )

        vehicle_state.update_battery_capacity.assert_called_once_with(0.0)
        pub.publish_float.assert_any_call(TOTAL_BATTERY_CAPACITY_STATE_TOPIC, 64.0)

    async def test_battery_capacity_skips_publish_when_no_default(self) -> None:
        """When `real_battery_capacity` returns None (unknown model), skip the publish."""
        handler, pub = _build()
        vehicle_state = cast("MagicMock", handler.vehicle_state)
        vehicle_state.vehicle.real_battery_capacity = None

        await handler.handle_mqtt_command(
            topic=TOTAL_BATTERY_CAPACITY_SET_TOPIC, payload="0", retained=False
        )

        vehicle_state.update_battery_capacity.assert_called_once_with(0.0)
        pub.publish_float.assert_not_called()

    async def test_retained_action_command_dropped_at_dispatcher(self) -> None:
        """Retained `/set` for an action-bearing command is dropped at the dispatcher.

        DrivetrainChargingCommand has not opted in via
        is_replayable_when_retained(). A retained replay of `charging/set` (e.g.
        from a non-HA client that mistakenly retained the topic) must NOT
        invoke the handler — otherwise the SAIC charging API call would re-fire
        on every gateway restart.
        """
        saic_api = AsyncMock()
        handler, pub = _build(saic_api=saic_api)

        await handler.handle_mqtt_command(
            topic=CHARGING_SET_TOPIC, payload="true", retained=True
        )

        # Handler never ran: no API call, no Success/result publish, no clear_topic
        saic_api.control_charging.assert_not_called()
        pub.publish_str.assert_not_called()
        pub.clear_topic.assert_not_called()
