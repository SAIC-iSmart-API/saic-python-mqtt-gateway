from __future__ import annotations

import datetime
import json
from typing import Any
import unittest
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
import pytest
from saic_ismart_client_ng.api.vehicle.schema import VinInfo
from saic_ismart_client_ng.api.vehicle_charging import (
    ChargeCurrentLimitCode,
    TargetBatteryCode,
)
from saic_ismart_client_ng.api.vehicle_charging.schema import (
    ScheduledBatteryHeatingResp,
)

from configuration import Configuration
from exceptions import VehicleStatusDriftException
import mqtt_topics
from vehicle import PollingPhase, RefreshMode, VehicleState
from vehicle_info import VehicleInfo

from .common_mocks import (
    DRIVETRAIN_MILEAGE,
    DRIVETRAIN_MILEAGE_OF_DAY,
    DRIVETRAIN_RANGE_BMS,
    DRIVETRAIN_RANGE_VEHICLE,
    DRIVETRAIN_SOC_BMS,
    DRIVETRAIN_SOC_VEHICLE,
    VIN,
    get_mock_charge_management_data_resp,
    get_mock_vehicle_status_resp,
)
from .mocks import MessageCapturingConsolePublisher


class TestVehicleState(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        config = Configuration()
        config.anonymized_publishing = False
        self.publisher = MessageCapturingConsolePublisher(config)
        vin_info = VinInfo()
        vin_info.vin = VIN
        vehicle_info = VehicleInfo(vin_info, None)
        account_prefix = f"/vehicles/{VIN}"
        scheduler = BlockingScheduler()
        self.vehicle_state = VehicleState(
            self.publisher, scheduler, account_prefix, vehicle_info
        )

    async def test_update_soc_with_no_bms_data(self) -> None:
        vehicle_status_resp = get_mock_vehicle_status_resp()
        result = self.vehicle_state.handle_vehicle_status(vehicle_status_resp)

        # Reset topics since we are only asserting the differences
        self.publisher.map.clear()

        self.vehicle_state.update_data_conflicting_in_vehicle_and_bms(
            vehicle_status=result, charge_status=None
        )
        self.assert_mqtt_topic(
            TestVehicleState.get_topic(mqtt_topics.DRIVETRAIN_SOC),
            float(DRIVETRAIN_SOC_VEHICLE),
        )
        self.assert_mqtt_topic(
            TestVehicleState.get_topic(mqtt_topics.DRIVETRAIN_RANGE),
            DRIVETRAIN_RANGE_VEHICLE,
        )
        self.assert_mqtt_topic(
            TestVehicleState.get_topic(mqtt_topics.DRIVETRAIN_HV_BATTERY_ACTIVE), True
        )
        expected_topics = {
            "/vehicles/vin10000000000000/drivetrain/hvBatteryActive",
            "/vehicles/vin10000000000000/refresh/lastActivity",
            "/vehicles/vin10000000000000/drivetrain/soc",
            "/vehicles/vin10000000000000/drivetrain/range",
        }
        assert expected_topics == set(self.publisher.map.keys())

    async def test_update_soc_with_bms_data(self) -> None:
        vehicle_status_resp = get_mock_vehicle_status_resp()
        chrg_mgmt_data_resp = get_mock_charge_management_data_resp()
        vehicle_status_resp_result = self.vehicle_state.handle_vehicle_status(
            vehicle_status_resp
        )
        chrg_mgmt_data_resp_result = self.vehicle_state.handle_charge_status(
            chrg_mgmt_data_resp
        )

        # Reset topics since we are only asserting the differences
        self.publisher.map.clear()

        self.vehicle_state.update_data_conflicting_in_vehicle_and_bms(
            vehicle_status=vehicle_status_resp_result,
            charge_status=chrg_mgmt_data_resp_result,
        )
        self.assert_mqtt_topic(
            TestVehicleState.get_topic(mqtt_topics.DRIVETRAIN_SOC), DRIVETRAIN_SOC_BMS
        )
        self.assert_mqtt_topic(
            TestVehicleState.get_topic(mqtt_topics.DRIVETRAIN_RANGE),
            DRIVETRAIN_RANGE_BMS,
        )
        self.assert_mqtt_topic(
            TestVehicleState.get_topic(mqtt_topics.DRIVETRAIN_HV_BATTERY_ACTIVE), True
        )
        expected_topics = {
            "/vehicles/vin10000000000000/drivetrain/hvBatteryActive",
            "/vehicles/vin10000000000000/refresh/lastActivity",
            "/vehicles/vin10000000000000/drivetrain/soc",
            "/vehicles/vin10000000000000/drivetrain/range",
        }
        assert expected_topics == set(self.publisher.map.keys())

    def assert_mqtt_topic(self, topic: str, value: Any) -> None:
        mqtt_map = self.publisher.map
        if topic in mqtt_map:
            if isinstance(value, float) or isinstance(mqtt_map[topic], float):
                assert value == pytest.approx(mqtt_map[topic], abs=0.1)
            else:
                assert value == mqtt_map[topic]
        else:
            self.fail(f"MQTT map does not contain topic {topic}")

    def test_handle_charge_status_with_phev_ignore_values(self) -> None:
        """PHEV vehicles send P_IGNORE (0) for target SOC and 0 for scheduled charging mode."""
        chrg_mgmt_data_resp = get_mock_charge_management_data_resp(
            bms_on_bd_chrg_trgt_soc_dsp_cmd=0,
            bms_reser_ctrl_dsp_cmd=0,
        )
        result = self.vehicle_state.handle_charge_status(chrg_mgmt_data_resp)

        assert result.target_soc is None
        assert result.scheduled_charging is None
        assert (
            self.get_topic(mqtt_topics.DRIVETRAIN_SOC_TARGET) not in self.publisher.map
        )

    def test_republish_command_states_after_configure_missing(self) -> None:
        self.vehicle_state.configure_missing()
        self.publisher.map.clear()

        self.vehicle_state.republish_command_states()

        self.assert_mqtt_topic(self.get_topic(mqtt_topics.REFRESH_PERIOD_ACTIVE), 30)
        self.assert_mqtt_topic(
            self.get_topic(mqtt_topics.REFRESH_PERIOD_INACTIVE), 86400
        )
        self.assert_mqtt_topic(
            self.get_topic(mqtt_topics.REFRESH_PERIOD_AFTER_SHUTDOWN), 120
        )
        self.assert_mqtt_topic(
            self.get_topic(mqtt_topics.REFRESH_PERIOD_INACTIVE_GRACE), 600
        )
        self.assert_mqtt_topic(
            self.get_topic(mqtt_topics.CLIMATE_REMOTE_TEMPERATURE), 22
        )
        self.assert_mqtt_topic(
            self.get_topic(mqtt_topics.REFRESH_MODE), RefreshMode.PERIODIC.value
        )

    def test_republish_command_states_skips_unset_values(self) -> None:
        self.vehicle_state.republish_command_states()

        # Refresh periods are -1 and optional values are None, so they should not be published
        assert (
            self.get_topic(mqtt_topics.REFRESH_PERIOD_ACTIVE) not in self.publisher.map
        )
        assert (
            self.get_topic(mqtt_topics.REFRESH_PERIOD_INACTIVE)
            not in self.publisher.map
        )
        assert (
            self.get_topic(mqtt_topics.REFRESH_PERIOD_AFTER_SHUTDOWN)
            not in self.publisher.map
        )
        assert (
            self.get_topic(mqtt_topics.REFRESH_PERIOD_INACTIVE_GRACE)
            not in self.publisher.map
        )
        assert (
            self.get_topic(mqtt_topics.DRIVETRAIN_SOC_TARGET) not in self.publisher.map
        )
        assert (
            self.get_topic(mqtt_topics.DRIVETRAIN_CHARGECURRENT_LIMIT)
            not in self.publisher.map
        )
        assert (
            self.get_topic(mqtt_topics.CLIMATE_REMOTE_TEMPERATURE)
            not in self.publisher.map
        )
        # refresh_mode defaults to RefreshMode.PERIODIC (never None), so it IS always published
        self.assert_mqtt_topic(
            self.get_topic(mqtt_topics.REFRESH_MODE), RefreshMode.PERIODIC.value
        )

    def test_configure_missing_skips_when_retained_value_present(self) -> None:
        """Sentinel guards in configure_missing preserve retained-replay values.

        Retained `/set` replay seeds in-memory state before configure_missing
        runs; configure_missing must then leave those values alone.
        """
        self.vehicle_state.set_refresh_period_active(45)
        self.vehicle_state.update_battery_capacity(50.0)

        self.vehicle_state.configure_missing()

        assert self.vehicle_state.refresh_period_active == 45
        assert self.vehicle_state.vehicle.custom_battery_capacity == 50.0

    def test_configure_missing_applies_defaults_when_no_retained(self) -> None:
        assert self.vehicle_state.refresh_period_active == -1
        self.vehicle_state.configure_missing()
        assert self.vehicle_state.refresh_period_active == 30
        assert self.vehicle_state.refresh_period_inactive == 86400
        assert self.vehicle_state.refresh_period_after_shutdown == 120
        assert self.vehicle_state.refresh_period_inactive_grace == 600

    def test_configure_missing_preserves_retained_off_refresh_mode(self) -> None:
        self.vehicle_state.set_refresh_mode(RefreshMode.OFF, "retained replay")
        self.vehicle_state.configure_missing()
        assert self.vehicle_state.refresh_mode == RefreshMode.OFF

    def test_republish_command_states_includes_api_values(self) -> None:
        self.vehicle_state.configure_missing()
        self.vehicle_state.update_target_soc(TargetBatteryCode.P_80)
        self.vehicle_state.update_charge_current_limit(ChargeCurrentLimitCode.C_MAX)
        self.publisher.map.clear()

        self.vehicle_state.republish_command_states()

        self.assert_mqtt_topic(
            self.get_topic(mqtt_topics.DRIVETRAIN_SOC_TARGET),
            TargetBatteryCode.P_80.percentage,
        )
        self.assert_mqtt_topic(
            self.get_topic(mqtt_topics.DRIVETRAIN_CHARGECURRENT_LIMIT),
            ChargeCurrentLimitCode.C_MAX.limit,
        )

    def test_battery_heating_decodes_with_user_timezone(self) -> None:
        """Battery heating time 15:30 CET stored as UTC epoch is decoded back to 15:30."""
        cet = ZoneInfo("Europe/Rome")
        self.vehicle_state.update_user_timezone(cet)

        # Create a UTC epoch for 15:30 CET today
        today = datetime.date.today()
        local_dt = datetime.datetime(
            today.year, today.month, today.day, 15, 30, tzinfo=cet
        )
        epoch_ms = int(local_dt.timestamp()) * 1000

        resp = ScheduledBatteryHeatingResp()
        resp.startTime = epoch_ms
        resp.status = 1

        self.vehicle_state.handle_scheduled_battery_heating_status(resp)

        topic = self.get_topic(mqtt_topics.DRIVETRAIN_BATTERY_HEATING_SCHEDULE)
        result = json.loads(self.publisher.map[topic])
        assert result["startTime"] == "15:30"
        assert result["mode"] == "on"

    def test_battery_heating_decodes_utc_timestamp_with_user_timezone(self) -> None:
        """08:00 CET (07:00 UTC) stored as epoch → decoded as 08:00."""
        cet = ZoneInfo("Europe/Rome")
        self.vehicle_state.update_user_timezone(cet)

        today = datetime.date.today()
        local_dt = datetime.datetime(
            today.year, today.month, today.day, 8, 0, tzinfo=cet
        )
        epoch_ms = int(local_dt.timestamp()) * 1000

        resp = ScheduledBatteryHeatingResp()
        resp.startTime = epoch_ms
        resp.status = 1

        self.vehicle_state.handle_scheduled_battery_heating_status(resp)

        topic = self.get_topic(mqtt_topics.DRIVETRAIN_BATTERY_HEATING_SCHEDULE)
        result = json.loads(self.publisher.map[topic])
        assert result["startTime"] == "08:00"
        assert result["mode"] == "on"

    def test_handle_vehicle_status_rejects_none_timestamp(self) -> None:
        resp = get_mock_vehicle_status_resp()
        resp.statusTime = None
        with pytest.raises(VehicleStatusDriftException, match="invalid timestamp"):
            self.vehicle_state.handle_vehicle_status(resp)

    def test_handle_vehicle_status_rejects_zero_timestamp(self) -> None:
        resp = get_mock_vehicle_status_resp()
        resp.statusTime = 0
        with pytest.raises(VehicleStatusDriftException, match="invalid timestamp"):
            self.vehicle_state.handle_vehicle_status(resp)

    def test_handle_vehicle_status_rejects_max_int32_timestamp(self) -> None:
        resp = get_mock_vehicle_status_resp()
        resp.statusTime = 2147483647
        with pytest.raises(VehicleStatusDriftException, match="invalid timestamp"):
            self.vehicle_state.handle_vehicle_status(resp)

    def test_handle_vehicle_status_rejects_drifted_timestamp(self) -> None:
        resp = get_mock_vehicle_status_resp()
        resp.statusTime = 1000000000  # 2001-09-09, well outside 15 min window
        with pytest.raises(
            VehicleStatusDriftException, match="drifted more than 15 minutes"
        ):
            self.vehicle_state.handle_vehicle_status(resp)

    def test_mileage_of_day_published_when_valid(self) -> None:
        """Mileage of day is published when it does not exceed total mileage."""
        vehicle_status_resp = get_mock_vehicle_status_resp()
        self.vehicle_state.handle_vehicle_status(vehicle_status_resp)
        chrg_mgmt_data_resp = get_mock_charge_management_data_resp()
        self.vehicle_state.handle_charge_status(chrg_mgmt_data_resp)

        self.assert_mqtt_topic(
            self.get_topic(mqtt_topics.DRIVETRAIN_MILEAGE_OF_DAY),
            DRIVETRAIN_MILEAGE_OF_DAY,
        )

    def test_mileage_of_day_skipped_when_exceeds_total(self) -> None:
        """Mileage of day should not be published when it exceeds total mileage."""
        vehicle_status_resp = get_mock_vehicle_status_resp()
        self.vehicle_state.handle_vehicle_status(vehicle_status_resp)

        chrg_mgmt_data_resp = get_mock_charge_management_data_resp()
        # Set mileageOfDay raw value higher than total mileage raw value
        assert chrg_mgmt_data_resp.rvsChargeStatus is not None
        chrg_mgmt_data_resp.rvsChargeStatus.mileageOfDay = (
            DRIVETRAIN_MILEAGE + 100
        ) * 10
        self.vehicle_state.handle_charge_status(chrg_mgmt_data_resp)

        assert (
            self.get_topic(mqtt_topics.DRIVETRAIN_MILEAGE_OF_DAY)
            not in self.publisher.map
        )

    def test_mileage_since_last_charge_skipped_when_exceeds_total(self) -> None:
        """Mileage since last charge should not be published when it exceeds total mileage."""
        vehicle_status_resp = get_mock_vehicle_status_resp()
        self.vehicle_state.handle_vehicle_status(vehicle_status_resp)

        chrg_mgmt_data_resp = get_mock_charge_management_data_resp()
        assert chrg_mgmt_data_resp.rvsChargeStatus is not None
        chrg_mgmt_data_resp.rvsChargeStatus.mileageSinceLastCharge = (
            DRIVETRAIN_MILEAGE + 100
        ) * 10
        self.vehicle_state.handle_charge_status(chrg_mgmt_data_resp)

        assert (
            self.get_topic(mqtt_topics.DRIVETRAIN_MILEAGE_SINCE_LAST_CHARGE)
            not in self.publisher.map
        )

    def test_mileage_of_day_published_when_no_vehicle_status_yet(self) -> None:
        """When vehicle status has never been fetched, partial mileage should still be published."""
        chrg_mgmt_data_resp = get_mock_charge_management_data_resp()
        self.vehicle_state.handle_charge_status(chrg_mgmt_data_resp)

        self.assert_mqtt_topic(
            self.get_topic(mqtt_topics.DRIVETRAIN_MILEAGE_OF_DAY),
            DRIVETRAIN_MILEAGE_OF_DAY,
        )

    def test_is_charging_true_to_false_resets_last_car_shutdown(self) -> None:
        """When is_charging transitions True -> False after significant power, last_car_shutdown is updated."""
        old_shutdown = self.vehicle_state.last_car_shutdown
        self.vehicle_state.is_charging = True
        # Simulate significant charging power detected via handle_charge_status
        self.vehicle_state._had_significant_charging_power = True
        self.vehicle_state.is_charging = False
        assert self.vehicle_state.last_car_shutdown > old_shutdown

    def test_is_charging_true_to_false_without_significant_power_does_not_reset(
        self,
    ) -> None:
        """When is_charging transitions True -> False without significant power, no reset."""
        old_shutdown = self.vehicle_state.last_car_shutdown
        self.vehicle_state.is_charging = True
        # No significant power flag set (e.g. OBC trickle)
        self.vehicle_state.is_charging = False
        assert self.vehicle_state.last_car_shutdown == old_shutdown

    def test_is_charging_false_to_false_does_not_reset_last_car_shutdown(self) -> None:
        """When is_charging stays False, last_car_shutdown is not updated."""
        old_shutdown = self.vehicle_state.last_car_shutdown
        self.vehicle_state.is_charging = False
        assert self.vehicle_state.last_car_shutdown == old_shutdown

    def test_is_charging_true_to_true_does_not_reset_last_car_shutdown(self) -> None:
        """When is_charging stays True, last_car_shutdown is not updated."""
        self.vehicle_state.is_charging = True
        old_shutdown = self.vehicle_state.last_car_shutdown
        self.vehicle_state.is_charging = True
        assert self.vehicle_state.last_car_shutdown == old_shutdown

    def test_should_refresh_off_publishes_off_phase(self) -> None:
        self.vehicle_state.configure_missing()
        self.vehicle_state.set_refresh_mode(RefreshMode.OFF, "test")
        self.publisher.map.clear()
        result = self.vehicle_state.should_refresh()
        assert result is False
        self.assert_mqtt_topic(
            self.get_topic(mqtt_topics.REFRESH_POLLING_PHASE),
            PollingPhase.OFF.value,
        )

    def test_should_refresh_force_publishes_force_phase(self) -> None:
        self.vehicle_state.configure_missing()
        self.vehicle_state.set_refresh_mode(RefreshMode.FORCE, "test")
        self.publisher.map.clear()
        result = self.vehicle_state.should_refresh()
        assert result is True
        self.assert_mqtt_topic(
            self.get_topic(mqtt_topics.REFRESH_POLLING_PHASE),
            PollingPhase.FORCE.value,
        )

    def test_should_refresh_charging_detection_resets_shutdown(self) -> None:
        self.vehicle_state.configure_missing()
        old_shutdown = self.vehicle_state.last_car_shutdown
        self.vehicle_state.set_refresh_mode(RefreshMode.CHARGING_DETECTION, "test")
        self.publisher.map.clear()
        result = self.vehicle_state.should_refresh()
        assert result is True
        assert self.vehicle_state.last_car_shutdown >= old_shutdown
        self.assert_mqtt_topic(
            self.get_topic(mqtt_topics.REFRESH_POLLING_PHASE),
            PollingPhase.CHARGING_DETECTION.value,
        )

    def test_should_refresh_charging_detection_reverts_to_previous(self) -> None:
        self.vehicle_state.configure_missing()
        # Previous mode is PERIODIC (set by configure_missing)
        self.vehicle_state.set_refresh_mode(RefreshMode.CHARGING_DETECTION, "test")
        self.vehicle_state.should_refresh()
        assert self.vehicle_state.refresh_mode == RefreshMode.PERIODIC

    def test_should_refresh_charging_detection_from_off_reverts_to_off(self) -> None:
        self.vehicle_state.configure_missing()
        self.vehicle_state.set_refresh_mode(RefreshMode.OFF, "test")
        self.vehicle_state.set_refresh_mode(RefreshMode.CHARGING_DETECTION, "test")
        self.vehicle_state.should_refresh()
        assert self.vehicle_state.refresh_mode == RefreshMode.OFF

    def test_periodic_inactive_publishes_inactive_phase(self) -> None:
        self.vehicle_state.configure_missing()
        # Ensure the car is inactive and grace period has passed
        self.vehicle_state.hv_battery_active = False
        self.vehicle_state.last_car_shutdown = datetime.datetime.min.replace(
            tzinfo=datetime.UTC
        )
        self.vehicle_state.last_car_activity = datetime.datetime.min.replace(
            tzinfo=datetime.UTC
        )
        self.vehicle_state.last_successful_refresh = datetime.datetime.now(
            tz=datetime.UTC
        )
        self.publisher.map.clear()
        result = self.vehicle_state.should_refresh()
        assert result is False
        self.assert_mqtt_topic(
            self.get_topic(mqtt_topics.REFRESH_POLLING_PHASE),
            PollingPhase.INACTIVE.value,
        )

    def test_periodic_after_shutdown_publishes_after_shutdown_phase(self) -> None:
        self.vehicle_state.configure_missing()
        # Car just shut down, grace period active
        self.vehicle_state.hv_battery_active = False
        self.vehicle_state.last_car_shutdown = datetime.datetime.now(tz=datetime.UTC)
        self.vehicle_state.last_car_activity = datetime.datetime.min.replace(
            tzinfo=datetime.UTC
        )
        self.vehicle_state.last_successful_refresh = datetime.datetime.now(
            tz=datetime.UTC
        )
        self.publisher.map.clear()
        result = self.vehicle_state.should_refresh()
        # Should not refresh yet (just refreshed) but phase should be after_shutdown
        assert result is False
        self.assert_mqtt_topic(
            self.get_topic(mqtt_topics.REFRESH_POLLING_PHASE),
            PollingPhase.AFTER_SHUTDOWN.value,
        )

    def test_charging_stop_triggers_after_shutdown_grace(self) -> None:
        """End-to-end: charging stops -> last_car_shutdown resets -> after_shutdown phase."""
        self.vehicle_state.configure_missing()
        # Car is parked (off), only charging keeps it "active"
        self.vehicle_state.hv_battery_active = False
        self.vehicle_state.is_charging = True
        self.vehicle_state._had_significant_charging_power = True
        self.vehicle_state.hv_battery_active = True
        # Simulate a recent successful refresh
        self.vehicle_state.last_successful_refresh = datetime.datetime.now(
            tz=datetime.UTC
        )
        self.vehicle_state.last_car_activity = datetime.datetime.min.replace(
            tzinfo=datetime.UTC
        )
        # Charging stops (e.g. phase switch) — car itself is off
        self.vehicle_state.is_charging = False
        self.vehicle_state.hv_battery_active = False
        self.publisher.map.clear()
        self.vehicle_state.should_refresh()
        # Grace period is now active, phase should be after_shutdown
        self.assert_mqtt_topic(
            self.get_topic(mqtt_topics.REFRESH_POLLING_PHASE),
            PollingPhase.AFTER_SHUTDOWN.value,
        )

    def test_polling_phase_not_republished_when_unchanged(self) -> None:
        """Calling should_refresh() twice with the same state should only publish the phase once."""
        self.vehicle_state.configure_missing()
        self.vehicle_state.set_refresh_mode(RefreshMode.OFF, "test")
        self.publisher.map.clear()
        self.publisher.publish_count.clear()

        self.vehicle_state.should_refresh()
        self.vehicle_state.should_refresh()

        phase_topic = self.get_topic(mqtt_topics.REFRESH_POLLING_PHASE)
        assert self.publisher.publish_count.get(phase_topic, 0) == 1

    def test_polling_phase_republished_after_transition_back(self) -> None:
        """A->B->A transition must publish all three phases (not suppress the return to A)."""
        self.vehicle_state.configure_missing()
        # Start with OFF (phase A)
        self.vehicle_state.set_refresh_mode(RefreshMode.OFF, "test")
        self.publisher.map.clear()
        self.publisher.publish_count.clear()

        # Phase A: OFF
        self.vehicle_state.should_refresh()
        phase_topic = self.get_topic(mqtt_topics.REFRESH_POLLING_PHASE)
        assert self.publisher.map[phase_topic] == PollingPhase.OFF.value
        assert self.publisher.publish_count[phase_topic] == 1

        # Phase B: FORCE (one-shot, reverts to PERIODIC)
        self.vehicle_state.set_refresh_mode(RefreshMode.FORCE, "test")
        self.vehicle_state.should_refresh()
        assert self.publisher.map[phase_topic] == PollingPhase.FORCE.value
        assert self.publisher.publish_count[phase_topic] == 2

        # Phase A again: back to OFF
        self.vehicle_state.set_refresh_mode(RefreshMode.OFF, "test")
        self.vehicle_state.should_refresh()
        assert self.publisher.map[phase_topic] == PollingPhase.OFF.value
        assert self.publisher.publish_count[phase_topic] == 3

    @staticmethod
    def get_topic(sub_topic: str) -> str:
        return f"/vehicles/{VIN}/{sub_topic}"
