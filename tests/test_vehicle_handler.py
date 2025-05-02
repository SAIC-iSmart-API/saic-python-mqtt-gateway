from __future__ import annotations

from typing import Any
import unittest
from unittest.mock import patch

from apscheduler.schedulers.blocking import BlockingScheduler
from common_mocks import (
    BMS_CHARGE_STATUS,
    CLIMATE_EXTERIOR_TEMPERATURE,
    CLIMATE_INTERIOR_TEMPERATURE,
    DOORS_BONNET,
    DOORS_BOOT,
    DOORS_DRIVER,
    DOORS_LOCKED,
    DOORS_PASSENGER,
    DOORS_REAR_LEFT,
    DOORS_REAR_RIGHT,
    DRIVETRAIN_AUXILIARY_BATTERY_VOLTAGE,
    DRIVETRAIN_CHARGER_CONNECTED,
    DRIVETRAIN_CHARGING,
    DRIVETRAIN_CHARGING_CABLE_LOCK,
    DRIVETRAIN_CHARGING_TYPE,
    DRIVETRAIN_CURRENT,
    DRIVETRAIN_HYBRID_ELECTRICAL_RANGE,
    DRIVETRAIN_LAST_CHARGE_ENDING_POWER,
    DRIVETRAIN_MILEAGE,
    DRIVETRAIN_MILEAGE_OF_DAY,
    DRIVETRAIN_MILEAGE_SINCE_LAST_CHARGE,
    DRIVETRAIN_POWER,
    DRIVETRAIN_REMAINING_CHARGING_TIME,
    DRIVETRAIN_RUNNING,
    DRIVETRAIN_SOC_KWH,
    DRIVETRAIN_VOLTAGE,
    LIGHTS_DIPPED_BEAM,
    LIGHTS_MAIN_BEAM,
    LIGHTS_SIDE,
    LOCATION_ELEVATION,
    LOCATION_HEADING,
    LOCATION_LATITUDE,
    LOCATION_LONGITUDE,
    LOCATION_SPEED,
    REAL_TOTAL_BATTERY_CAPACITY,
    TYRES_FRONT_LEFT_PRESSURE,
    TYRES_FRONT_RIGHT_PRESSURE,
    TYRES_REAR_LEFT_PRESSURE,
    TYRES_REAR_RIGHT_PRESSURE,
    VIN,
    WINDOWS_DRIVER,
    WINDOWS_PASSENGER,
    WINDOWS_REAR_LEFT,
    WINDOWS_REAR_RIGHT,
    WINDOWS_SUN_ROOF,
    get_mock_charge_management_data_resp,
    get_mock_vehicle_status_resp,
)
from mocks import MessageCapturingConsolePublisher
import pytest
from saic_ismart_client_ng import SaicApi
from saic_ismart_client_ng.api.vehicle.schema import (
    VehicleModelConfiguration,
    VinInfo,
)
from saic_ismart_client_ng.model import SaicApiConfiguration

from configuration import Configuration
from handlers.relogin import ReloginHandler
from mqtt_gateway import VehicleHandler
import mqtt_topics
from vehicle import VehicleState
from vehicle_info import VehicleInfo


class TestVehicleHandler(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        config = Configuration()
        config.anonymized_publishing = False
        self.saicapi = SaicApi(
            configuration=SaicApiConfiguration(
                username="aaa@nowhere.org",
                password="xxxxxxxxx",  # noqa: S106
            ),
            listener=None,
        )
        self.publisher = MessageCapturingConsolePublisher(config)
        vin_info = VinInfo()
        vin_info.vin = VIN
        vin_info.series = "EH32 S"
        vin_info.modelName = "MG4 Electric"
        vin_info.modelYear = "2022"
        vin_info.vehicleModelConfiguration = [
            VehicleModelConfiguration("BATTERY", "BATTERY", "1"),
            VehicleModelConfiguration("BType", "Battery", "1"),
        ]
        vehicle_info = VehicleInfo(vin_info, None)
        account_prefix = f"/vehicles/{VIN}"
        scheduler = BlockingScheduler()
        vehicle_state = VehicleState(
            self.publisher, scheduler, account_prefix, vehicle_info
        )
        mock_relogin_handler = ReloginHandler(
            relogin_relay=30, api=self.saicapi, scheduler=None
        )
        self.vehicle_handler = VehicleHandler(
            config,
            mock_relogin_handler,
            self.saicapi,
            self.publisher,
            vehicle_info,
            vehicle_state,
        )

    async def test_update_vehicle_status(self) -> None:
        with patch.object(
            self.saicapi, "get_vehicle_status"
        ) as mock_get_vehicle_status:
            mock_get_vehicle_status.return_value = get_mock_vehicle_status_resp()
            await self.vehicle_handler.update_vehicle_status()

        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_RUNNING),
            DRIVETRAIN_RUNNING,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(
                mqtt_topics.DRIVETRAIN_AUXILIARY_BATTERY_VOLTAGE
            ),
            DRIVETRAIN_AUXILIARY_BATTERY_VOLTAGE,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_MILEAGE),
            DRIVETRAIN_MILEAGE,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.CLIMATE_INTERIOR_TEMPERATURE),
            CLIMATE_INTERIOR_TEMPERATURE,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.CLIMATE_EXTERIOR_TEMPERATURE),
            CLIMATE_EXTERIOR_TEMPERATURE,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE), "on"
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.CLIMATE_BACK_WINDOW_HEAT), "on"
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.LOCATION_SPEED), LOCATION_SPEED
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.LOCATION_HEADING), LOCATION_HEADING
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.LOCATION_LATITUDE),
            LOCATION_LATITUDE,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.LOCATION_LONGITUDE),
            LOCATION_LONGITUDE,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.LOCATION_ELEVATION),
            LOCATION_ELEVATION,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.WINDOWS_DRIVER), WINDOWS_DRIVER
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.WINDOWS_PASSENGER),
            WINDOWS_PASSENGER,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.WINDOWS_REAR_LEFT),
            WINDOWS_REAR_LEFT,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.WINDOWS_REAR_RIGHT),
            WINDOWS_REAR_RIGHT,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.WINDOWS_SUN_ROOF), WINDOWS_SUN_ROOF
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.DOORS_LOCKED), DOORS_LOCKED
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.DOORS_DRIVER), DOORS_DRIVER
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.DOORS_PASSENGER), DOORS_PASSENGER
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.DOORS_REAR_LEFT), DOORS_REAR_LEFT
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.DOORS_REAR_RIGHT), DOORS_REAR_RIGHT
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.DOORS_BONNET), DOORS_BONNET
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.DOORS_BOOT), DOORS_BOOT
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.TYRES_FRONT_LEFT_PRESSURE),
            TYRES_FRONT_LEFT_PRESSURE,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.TYRES_FRONT_RIGHT_PRESSURE),
            TYRES_FRONT_RIGHT_PRESSURE,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.TYRES_REAR_LEFT_PRESSURE),
            TYRES_REAR_LEFT_PRESSURE,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.TYRES_REAR_RIGHT_PRESSURE),
            TYRES_REAR_RIGHT_PRESSURE,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.LIGHTS_MAIN_BEAM), LIGHTS_MAIN_BEAM
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.LIGHTS_DIPPED_BEAM),
            LIGHTS_DIPPED_BEAM,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.LIGHTS_SIDE), LIGHTS_SIDE
        )
        expected_topics = {
            "/vehicles/vin10000000000000/drivetrain/running",
            "/vehicles/vin10000000000000/climate/interiorTemperature",
            "/vehicles/vin10000000000000/climate/exteriorTemperature",
            "/vehicles/vin10000000000000/drivetrain/auxiliaryBatteryVoltage",
            "/vehicles/vin10000000000000/location/heading",
            "/vehicles/vin10000000000000/location/latitude",
            "/vehicles/vin10000000000000/location/longitude",
            "/vehicles/vin10000000000000/location/elevation",
            "/vehicles/vin10000000000000/location/position",
            "/vehicles/vin10000000000000/location/speed",
            "/vehicles/vin10000000000000/windows/driver",
            "/vehicles/vin10000000000000/windows/passenger",
            "/vehicles/vin10000000000000/windows/rearLeft",
            "/vehicles/vin10000000000000/windows/rearRight",
            "/vehicles/vin10000000000000/windows/sunRoof",
            "/vehicles/vin10000000000000/doors/locked",
            "/vehicles/vin10000000000000/doors/driver",
            "/vehicles/vin10000000000000/doors/passenger",
            "/vehicles/vin10000000000000/doors/rearLeft",
            "/vehicles/vin10000000000000/doors/rearRight",
            "/vehicles/vin10000000000000/doors/bonnet",
            "/vehicles/vin10000000000000/doors/boot",
            "/vehicles/vin10000000000000/tyres/frontLeftPressure",
            "/vehicles/vin10000000000000/tyres/frontRightPressure",
            "/vehicles/vin10000000000000/tyres/rearLeftPressure",
            "/vehicles/vin10000000000000/tyres/rearRightPressure",
            "/vehicles/vin10000000000000/lights/mainBeam",
            "/vehicles/vin10000000000000/lights/dippedBeam",
            "/vehicles/vin10000000000000/lights/side",
            "/vehicles/vin10000000000000/climate/remoteClimateState",
            "/vehicles/vin10000000000000/climate/rearWindowDefrosterHeating",
            "/vehicles/vin10000000000000/climate/heatedSeatsFrontLeftLevel",
            "/vehicles/vin10000000000000/climate/heatedSeatsFrontRightLevel",
            "/vehicles/vin10000000000000/drivetrain/mileage",
            "/vehicles/vin10000000000000/refresh/lastVehicleState",
        }
        assert expected_topics == set(self.publisher.map.keys())

    async def test_update_charge_status(self) -> None:
        with patch.object(
            self.saicapi, "get_vehicle_charging_management_data"
        ) as mock_get_vehicle_charging_management_data:
            mock_get_vehicle_charging_management_data.return_value = (
                get_mock_charge_management_data_resp()
            )
            await self.vehicle_handler.update_charge_status()

        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_CHARGING),
            DRIVETRAIN_CHARGING,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_CURRENT),
            DRIVETRAIN_CURRENT,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_VOLTAGE),
            DRIVETRAIN_VOLTAGE,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_POWER), DRIVETRAIN_POWER
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(
                mqtt_topics.DRIVETRAIN_HYBRID_ELECTRICAL_RANGE
            ),
            DRIVETRAIN_HYBRID_ELECTRICAL_RANGE,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_MILEAGE_OF_DAY),
            DRIVETRAIN_MILEAGE_OF_DAY,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(
                mqtt_topics.DRIVETRAIN_MILEAGE_SINCE_LAST_CHARGE
            ),
            DRIVETRAIN_MILEAGE_SINCE_LAST_CHARGE,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_SOC_KWH),
            DRIVETRAIN_SOC_KWH,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_CHARGING_TYPE),
            DRIVETRAIN_CHARGING_TYPE,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_CHARGER_CONNECTED),
            DRIVETRAIN_CHARGER_CONNECTED,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(
                mqtt_topics.DRIVETRAIN_REMAINING_CHARGING_TIME
            ),
            DRIVETRAIN_REMAINING_CHARGING_TIME,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(
                mqtt_topics.DRIVETRAIN_LAST_CHARGE_ENDING_POWER
            ),
            DRIVETRAIN_LAST_CHARGE_ENDING_POWER,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_TOTAL_BATTERY_CAPACITY),
            REAL_TOTAL_BATTERY_CAPACITY,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_CHARGING_CABLE_LOCK),
            DRIVETRAIN_CHARGING_CABLE_LOCK,
        )
        self.assert_mqtt_topic(
            TestVehicleHandler.get_topic(mqtt_topics.BMS_CHARGE_STATUS),
            BMS_CHARGE_STATUS,
        )
        expected_topics = {
            "/vehicles/vin10000000000000/drivetrain/charging",
            "/vehicles/vin10000000000000/drivetrain/current",
            "/vehicles/vin10000000000000/drivetrain/voltage",
            "/vehicles/vin10000000000000/drivetrain/power",
            "/vehicles/vin10000000000000/obc/current",
            "/vehicles/vin10000000000000/obc/voltage",
            "/vehicles/vin10000000000000/drivetrain/hybrid_electrical_range",
            "/vehicles/vin10000000000000/drivetrain/mileageOfTheDay",
            "/vehicles/vin10000000000000/drivetrain/mileageSinceLastCharge",
            "/vehicles/vin10000000000000/drivetrain/chargingType",
            "/vehicles/vin10000000000000/drivetrain/chargerConnected",
            "/vehicles/vin10000000000000/drivetrain/remainingChargingTime",
            "/vehicles/vin10000000000000/refresh/lastChargeState",
            "/vehicles/vin10000000000000/drivetrain/totalBatteryCapacity",
            "/vehicles/vin10000000000000/drivetrain/soc_kwh",
            "/vehicles/vin10000000000000/drivetrain/lastChargeEndingPower",
            "/vehicles/vin10000000000000/drivetrain/batteryHeating",
            "/vehicles/vin10000000000000/drivetrain/chargingCableLock",
            "/vehicles/vin10000000000000/bms/chargeStatus",
            "/vehicles/vin10000000000000/refresh/period/charging",
        }
        assert expected_topics == set(self.publisher.map.keys())

    # Note: The closer the decorator is to the function definition, the earlier it is in the parameter list
    async def test_should_not_publish_same_data_twice(self) -> None:
        with patch.object(
            self.saicapi, "get_vehicle_charging_management_data"
        ) as mock_get_vehicle_charging_management_data:
            mock_get_vehicle_charging_management_data.return_value = (
                get_mock_charge_management_data_resp()
            )
            with patch.object(
                self.saicapi, "get_vehicle_status"
            ) as mock_get_vehicle_status:
                mock_get_vehicle_status.return_value = get_mock_vehicle_status_resp()

                await self.vehicle_handler.update_vehicle_status()
                vehicle_mqtt_map = dict(self.publisher.map.items())
                self.publisher.map.clear()

                await self.vehicle_handler.update_charge_status()
                charge_data_mqtt_map = dict(self.publisher.map.items())
                self.publisher.map.clear()

        common_data = set(vehicle_mqtt_map.keys()).intersection(
            set(charge_data_mqtt_map.keys())
        )

        assert len(common_data) == 0, (
            f"Some topics have been published from both car state and BMS state: {common_data!s}"
        )

    def assert_mqtt_topic(self, topic: str, value: Any) -> None:
        mqtt_map = self.publisher.map
        if topic in mqtt_map:
            if isinstance(value, float) or isinstance(mqtt_map[topic], float):
                assert value == pytest.approx(mqtt_map[topic], abs=0.1)
            else:
                assert value == mqtt_map[topic]
        else:
            self.fail(f"MQTT map does not contain topic {topic}")

    @staticmethod
    def get_topic(sub_topic: str) -> str:
        return f"/vehicles/{VIN}/{sub_topic}"
