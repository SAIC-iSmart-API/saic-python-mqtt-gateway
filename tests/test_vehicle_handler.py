from unittest import TestCase
from unittest.mock import patch

from saic_ismart_client.common_model import MessageV2, MessageBodyV2
from saic_ismart_client.ota_v1_1.data_model import VinInfo
from saic_ismart_client.ota_v2_1.data_model import OtaRvmVehicleStatusResp25857, \
    RvsBasicStatus25857, RvsPosition, RvsWayPoint, RvsWgs84Point
from saic_ismart_client.ota_v3_0.Message import MessageV30, MessageBodyV30
from saic_ismart_client.ota_v3_0.data_model import OtaChrgMangDataResp, RvsChargingStatus
from saic_ismart_client.saic_api import SaicApi

import mqtt_topics
from configuration import Configuration
from mqtt_gateway import VehicleHandler
from publisher import Publisher
from vehicle import VehicleState

VIN = 'vin10000000000000'

DRIVETRAIN_RUNNING = False
DRIVETRAIN_CHARGING = True
DRIVETRAIN_AUXILIARY_BATTERY_VOLTAGE = 42
DRIVETRAIN_MILEAGE = 4000
DRIVETRAIN_RANGE = 250
DRIVETRAIN_CURRENT = 42
DRIVETRAIN_VOLTAGE = 42
DRIVETRAIN_POWER = 1.764
DRIVETRAIN_SOC = 96
DRIVETRAIN_HYBRID_ELECTRICAL_RANGE = 0
DRIVETRAIN_MILEAGE_OF_DAY = 200
DRIVETRAIN_MILEAGE_SINCE_LAST_CHARGE = 5
DRIVETRAIN_SOC_KWH = 42
DRIVETRAIN_CHARGING_TYPE = 1
DRIVETRAIN_CHARGER_CONNECTED = True
DRIVETRAIN_LAST_CHARGE_ENDING_POWER = 200
DRIVETRAIN_TOTAL_BATTERY_CAPACITY = 500

CLIMATE_INTERIOR_TEMPERATURE = 22
CLIMATE_EXTERIOR_TEMPERATURE = 18
CLIMATE_REMOTE_CLIMATE_STATE = 2
CLIMATE_BACK_WINDOW_HEAT = 7

LOCATION_SPEED = 0.0
LOCATION_HEADING = 42
LOCATION_LATITUDE = 48.8584
LOCATION_LONGITUDE = 22.945
LOCATION_ELEVATION = 200

WINDOWS_DRIVER = False
WINDOWS_PASSENGER = False
WINDOWS_REAR_LEFT = False
WINDOWS_REAR_RIGHT = False
WINDOWS_SUN_ROOF = False

DOORS_LOCKED = True
DOORS_DRIVER = False
DOORS_PASSENGER = False
DOORS_REAR_LEFT = False
DOORS_REAR_RIGHT = False
DOORS_BONNET = False
DOORS_BOOT = False

TYRES_FRONT_LEFT_PRESSURE = 2.8
TYRES_FRONT_RIGHT_PRESSURE = 2.8
TYRES_REAR_LEFT_PRESSURE = 2.8
TYRES_REAR_RIGHT_PRESSURE = 2.8

LIGHTS_MAIN_BEAM = False
LIGHTS_DIPPED_BEAM = False


def mock_vehicle_status(mocked_vehicle_status):
    vehicle_status_resp = OtaRvmVehicleStatusResp25857()
    vehicle_status_req_msg = MessageV2(MessageBodyV2(), vehicle_status_resp)
    basic_vehicle_status = RvsBasicStatus25857()
    vehicle_status_resp.basic_vehicle_status = basic_vehicle_status
    basic_vehicle_status.engine_status = 0
    basic_vehicle_status.extended_data2 = 2
    basic_vehicle_status.battery_voltage = DRIVETRAIN_AUXILIARY_BATTERY_VOLTAGE * 10
    basic_vehicle_status.mileage = DRIVETRAIN_MILEAGE * 10
    basic_vehicle_status.fuel_range_elec = DRIVETRAIN_RANGE * 10

    basic_vehicle_status.interior_temperature = CLIMATE_INTERIOR_TEMPERATURE
    basic_vehicle_status.exterior_temperature = CLIMATE_EXTERIOR_TEMPERATURE
    basic_vehicle_status.remote_climate_status = CLIMATE_REMOTE_CLIMATE_STATE
    basic_vehicle_status.rmt_htd_rr_wnd_st = CLIMATE_BACK_WINDOW_HEAT

    gps_position = RvsPosition()
    way_point = RvsWayPoint()
    way_point.speed = LOCATION_SPEED * 10
    way_point.heading = LOCATION_HEADING
    position = RvsWgs84Point()
    position.latitude = LOCATION_LATITUDE * 1000000
    position.longitude = LOCATION_LONGITUDE * 1000000
    position.altitude = LOCATION_ELEVATION
    way_point.position = position
    gps_position.way_point = way_point
    vehicle_status_resp.gps_position = gps_position

    basic_vehicle_status.driver_window = WINDOWS_DRIVER
    basic_vehicle_status.passenger_window = WINDOWS_PASSENGER
    basic_vehicle_status.rear_left_window = WINDOWS_REAR_LEFT
    basic_vehicle_status.rear_right_window = WINDOWS_REAR_RIGHT
    basic_vehicle_status.sun_roof_status = WINDOWS_SUN_ROOF

    basic_vehicle_status.lock_status = DOORS_LOCKED
    basic_vehicle_status.driver_door = DOORS_DRIVER
    basic_vehicle_status.passenger_door = DOORS_PASSENGER
    basic_vehicle_status.rear_left_door = DOORS_REAR_LEFT
    basic_vehicle_status.rear_right_door = DOORS_REAR_RIGHT
    basic_vehicle_status.bonnet_status = DOORS_BONNET
    basic_vehicle_status.boot_status = DOORS_BOOT

    basic_vehicle_status.front_left_tyre_pressure = TYRES_FRONT_LEFT_PRESSURE * 25
    basic_vehicle_status.front_right_tyre_pressure = TYRES_FRONT_RIGHT_PRESSURE * 25
    basic_vehicle_status.rear_left_tyre_pressure = TYRES_REAR_LEFT_PRESSURE * 25
    basic_vehicle_status.rear_right_tyre_pressure = TYRES_REAR_RIGHT_PRESSURE * 25

    basic_vehicle_status.main_beam_status = LIGHTS_MAIN_BEAM
    basic_vehicle_status.dipped_beam_status = LIGHTS_DIPPED_BEAM

    mocked_vehicle_status.return_value = vehicle_status_req_msg


def mock_charge_status(mocked_charge_status):
    charge_mgmt_data = OtaChrgMangDataResp()
    charge_mgmt_data.bmsPackCrnt = (DRIVETRAIN_CURRENT + 1000.0) * 20
    charge_mgmt_data.bmsPackVol = DRIVETRAIN_VOLTAGE * 4
    charge_mgmt_data.bmsPackSOCDsp = DRIVETRAIN_SOC * 10.0
    charge_mgmt_data.bms_estd_elec_rng = DRIVETRAIN_HYBRID_ELECTRICAL_RANGE * 10.0
    charge_status = RvsChargingStatus()
    charge_status.mileage_of_day = DRIVETRAIN_MILEAGE_OF_DAY * 10.0
    charge_status.mileage_since_last_charge = DRIVETRAIN_MILEAGE_SINCE_LAST_CHARGE * 10.0
    charge_status.real_time_power = DRIVETRAIN_SOC_KWH * 10.0
    charge_status.charging_type = DRIVETRAIN_CHARGING_TYPE
    charge_status.charging_gun_state = DRIVETRAIN_CHARGER_CONNECTED
    charge_status.last_charge_ending_power = DRIVETRAIN_LAST_CHARGE_ENDING_POWER * 10.0
    charge_status.total_battery_capacity = DRIVETRAIN_TOTAL_BATTERY_CAPACITY * 10.0
    charge_mgmt_data.chargeStatus = charge_status
    charge_mgmt_data_rsp_msg = MessageV30(MessageBodyV30(), charge_mgmt_data)
    mocked_charge_status.return_value = charge_mgmt_data_rsp_msg


class TestVehicleHandler(TestCase):
    def setUp(self) -> None:
        config = Configuration()
        saicapi = SaicApi('', '', '')
        publisher = Publisher(config)
        vin_info = VinInfo()
        vin_info.vin = VIN
        account_prefix = f'/vehicles/{VIN}'
        vehicle_state = VehicleState(publisher, account_prefix, VIN)
        self.vehicle_handler = VehicleHandler(config, saicapi, publisher, vin_info, vehicle_state)

    @patch.object(SaicApi, 'get_vehicle_status_with_retry')
    def test_update_vehicle_status(self, mocked_vehicle_status):
        mock_vehicle_status(mocked_vehicle_status)
        self.vehicle_handler.update_vehicle_status()

        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_RUNNING), DRIVETRAIN_RUNNING)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_CHARGING), DRIVETRAIN_CHARGING)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_AUXILIARY_BATTERY_VOLTAGE),
                               DRIVETRAIN_AUXILIARY_BATTERY_VOLTAGE)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_MILEAGE), DRIVETRAIN_MILEAGE)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_RANGE), DRIVETRAIN_RANGE)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.CLIMATE_INTERIOR_TEMPERATURE),
                               CLIMATE_INTERIOR_TEMPERATURE)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.CLIMATE_EXTERIOR_TEMPERATURE),
                               CLIMATE_EXTERIOR_TEMPERATURE)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE),
                               'on')
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.CLIMATE_BACK_WINDOW_HEAT),
                               CLIMATE_BACK_WINDOW_HEAT)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.LOCATION_SPEED), LOCATION_SPEED)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.LOCATION_HEADING), LOCATION_HEADING)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.LOCATION_LATITUDE), LOCATION_LATITUDE)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.LOCATION_LONGITUDE), LOCATION_LONGITUDE)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.LOCATION_ELEVATION), LOCATION_ELEVATION)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.WINDOWS_DRIVER), WINDOWS_DRIVER)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.WINDOWS_PASSENGER), WINDOWS_PASSENGER)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.WINDOWS_REAR_LEFT), WINDOWS_REAR_LEFT)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.WINDOWS_REAR_RIGHT), WINDOWS_REAR_RIGHT)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.WINDOWS_SUN_ROOF), WINDOWS_SUN_ROOF)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DOORS_LOCKED), DOORS_LOCKED)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DOORS_DRIVER), DOORS_DRIVER)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DOORS_PASSENGER), DOORS_PASSENGER)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DOORS_REAR_LEFT), DOORS_REAR_LEFT)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DOORS_REAR_RIGHT), DOORS_REAR_RIGHT)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DOORS_BONNET), DOORS_BONNET)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DOORS_BOOT), DOORS_BOOT)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.TYRES_FRONT_LEFT_PRESSURE),
                               TYRES_FRONT_LEFT_PRESSURE)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.TYRES_FRONT_RIGHT_PRESSURE),
                               TYRES_FRONT_RIGHT_PRESSURE)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.TYRES_REAR_LEFT_PRESSURE),
                               TYRES_REAR_LEFT_PRESSURE)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.TYRES_REAR_RIGHT_PRESSURE),
                               TYRES_REAR_RIGHT_PRESSURE)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.LIGHTS_MAIN_BEAM), LIGHTS_MAIN_BEAM)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.LIGHTS_DIPPED_BEAM), LIGHTS_DIPPED_BEAM)
        self.assertEqual(36, len(self.vehicle_handler.publisher.map))

    @patch.object(SaicApi, 'get_charging_status')
    def test_update_charge_status(self, mocked_charge_status):
        mock_charge_status(mocked_charge_status)
        self.vehicle_handler.update_charge_status()

        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_CURRENT), DRIVETRAIN_CURRENT)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_VOLTAGE), DRIVETRAIN_VOLTAGE)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_POWER), DRIVETRAIN_POWER)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_SOC), DRIVETRAIN_SOC)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_HYBRID_ELECTRICAL_RANGE),
                               DRIVETRAIN_HYBRID_ELECTRICAL_RANGE)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_MILEAGE_OF_DAY),
                               DRIVETRAIN_MILEAGE_OF_DAY)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_MILEAGE_SINCE_LAST_CHARGE),
                               DRIVETRAIN_MILEAGE_SINCE_LAST_CHARGE)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_SOC_KWH), DRIVETRAIN_SOC_KWH)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_CHARGING_TYPE),
                               DRIVETRAIN_CHARGING_TYPE)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_CHARGER_CONNECTED),
                               DRIVETRAIN_CHARGER_CONNECTED)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_LAST_CHARGE_ENDING_POWER),
                               DRIVETRAIN_LAST_CHARGE_ENDING_POWER)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_TOTAL_BATTERY_CAPACITY),
                               DRIVETRAIN_TOTAL_BATTERY_CAPACITY)
        self.assertEqual(13, len(self.vehicle_handler.publisher.map))

    def assert_mqtt_topic(self, topic: str, value):
        mqtt_map = self.vehicle_handler.publisher.map
        if topic in mqtt_map:
            self.assertEqual(value, mqtt_map[topic])
        else:
            self.fail(f'MQTT map does not contain topic {topic}')

    @staticmethod
    def get_topic(sub_topic: str) -> str:
        return f'/vehicles/{VIN}/{sub_topic}'
