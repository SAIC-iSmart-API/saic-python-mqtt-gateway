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
from vehicle import RefreshMode, VehicleState
from vehicle_info import VehicleInfo

from .common_mocks import (
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
        # refresh_mode defaults to RefreshMode.OFF (never None), so it IS always published
        self.assert_mqtt_topic(
            self.get_topic(mqtt_topics.REFRESH_MODE), RefreshMode.OFF.value
        )

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
        with pytest.raises(VehicleStatusDriftException, match="drifted more than 15 minutes"):
            self.vehicle_state.handle_vehicle_status(resp)

    @staticmethod
    def get_topic(sub_topic: str) -> str:
        return f"/vehicles/{VIN}/{sub_topic}"
