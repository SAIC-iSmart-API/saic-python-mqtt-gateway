import time
import unittest
from unittest.mock import patch

from apscheduler.schedulers.blocking import BlockingScheduler
from saic_ismart_client_ng import SaicApi
from saic_ismart_client_ng.api.schema import GpsPosition, GpsStatus
from saic_ismart_client_ng.api.vehicle import VehicleStatusResp
from saic_ismart_client_ng.api.vehicle.schema import VinInfo, BasicVehicleStatus
from saic_ismart_client_ng.api.vehicle_charging import ChrgMgmtDataResp
from saic_ismart_client_ng.api.vehicle_charging.schema import RvsChargeStatus, ChrgMgmtData
from saic_ismart_client_ng.model import SaicApiConfiguration

import mqtt_topics
from configuration import Configuration
from mqtt_gateway import VehicleHandler
from publisher.log_publisher import Logger
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
DRIVETRAIN_REMAINING_CHARGING_TIME = 0
DRIVETRAIN_LAST_CHARGE_ENDING_POWER = 200
DRIVETRAIN_CHARGING_CABLE_LOCK = 1
REAL_TOTAL_BATTERY_CAPACITY = 64.0
RAW_TOTAL_BATTERY_CAPACITY = 72.5
BATTERY_CAPACITY_CORRECTION_FACTOR = REAL_TOTAL_BATTERY_CAPACITY / RAW_TOTAL_BATTERY_CAPACITY

CLIMATE_INTERIOR_TEMPERATURE = 22
CLIMATE_EXTERIOR_TEMPERATURE = 18
CLIMATE_REMOTE_CLIMATE_STATE = 2
CLIMATE_BACK_WINDOW_HEAT = 1

LOCATION_SPEED = 2.0
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
LIGHTS_SIDE = False


def mock_vehicle_status(mocked_vehicle_status):
    vehicle_status_resp = VehicleStatusResp(
        statusTime=int(time.time()),
        basicVehicleStatus=BasicVehicleStatus(
            engineStatus=0,
            extendedData2=2,
            batteryVoltage=DRIVETRAIN_AUXILIARY_BATTERY_VOLTAGE * 10,
            mileage=DRIVETRAIN_MILEAGE * 10,
            fuelRangeElec=DRIVETRAIN_RANGE * 10,
            interiorTemperature=CLIMATE_INTERIOR_TEMPERATURE,
            exteriorTemperature=CLIMATE_EXTERIOR_TEMPERATURE,
            remoteClimateStatus=CLIMATE_REMOTE_CLIMATE_STATE,
            rmtHtdRrWndSt=CLIMATE_BACK_WINDOW_HEAT,
            driverWindow=WINDOWS_DRIVER,
            passengerWindow=WINDOWS_PASSENGER,
            rearLeftWindow=WINDOWS_REAR_LEFT,
            rearRightWindow=WINDOWS_REAR_RIGHT,
            sunroofStatus=WINDOWS_SUN_ROOF,
            lockStatus=DOORS_LOCKED,
            driverDoor=DOORS_DRIVER,
            passengerDoor=DOORS_PASSENGER,
            rearRightDoor=DOORS_REAR_RIGHT,
            rearLeftDoor=DOORS_REAR_LEFT,
            bootStatus=DOORS_BOOT,
            frontLeftTyrePressure=int(TYRES_FRONT_LEFT_PRESSURE * 25),
            frontRightTyrePressure=int(TYRES_FRONT_RIGHT_PRESSURE * 25),
            rearLeftTyrePressure=int(TYRES_REAR_LEFT_PRESSURE * 25),
            rearRightTyrePressure=int(TYRES_REAR_RIGHT_PRESSURE * 25),
            mainBeamStatus=LIGHTS_MAIN_BEAM,
            dippedBeamStatus=LIGHTS_DIPPED_BEAM,
            sideLightStatus=LIGHTS_SIDE,
            frontLeftSeatHeatLevel=0,
            frontRightSeatHeatLevel=1
        ),
        gpsPosition=GpsPosition(
            gpsStatus=GpsStatus.FIX_3d.value,
            timeStamp=42,
            wayPoint=GpsPosition.WayPoint(
                position=GpsPosition.WayPoint.Position(
                    latitude=int(LOCATION_LATITUDE * 1000000),
                    longitude=int(LOCATION_LONGITUDE * 1000000),
                    altitude=LOCATION_ELEVATION
                ),
                heading=LOCATION_HEADING,
                hdop=0,
                satellites=3,
                speed=20,
            )
        )
    )

    mocked_vehicle_status.return_value = vehicle_status_resp


def mock_charge_status(mocked_charge_status):
    charge_mgmt_data_rsp_msg = ChrgMgmtDataResp(
        chrgMgmtData=ChrgMgmtData(
            bmsPackCrntV=0,
            bmsPackCrnt=int((DRIVETRAIN_CURRENT + 1000.0) * 20),
            bmsPackVol=DRIVETRAIN_VOLTAGE * 4,
            bmsPackSOCDsp=int(DRIVETRAIN_SOC * 10.0),
            bmsEstdElecRng=int(DRIVETRAIN_HYBRID_ELECTRICAL_RANGE * 10.0),
            ccuEleccLckCtrlDspCmd=1
        ),
        rvsChargeStatus=RvsChargeStatus(
            mileageOfDay=int(DRIVETRAIN_MILEAGE_OF_DAY * 10.0),
            mileageSinceLastCharge=int(DRIVETRAIN_MILEAGE_SINCE_LAST_CHARGE * 10.0),
            realtimePower=int((DRIVETRAIN_SOC_KWH / BATTERY_CAPACITY_CORRECTION_FACTOR) * 10),
            chargingType=DRIVETRAIN_CHARGING_TYPE,
            chargingGunState=DRIVETRAIN_CHARGER_CONNECTED,
            lastChargeEndingPower=int(
                (DRIVETRAIN_LAST_CHARGE_ENDING_POWER / BATTERY_CAPACITY_CORRECTION_FACTOR) * 10.0),
            totalBatteryCapacity=int(RAW_TOTAL_BATTERY_CAPACITY * 10.0)
        ),

    )
    mocked_charge_status.return_value = charge_mgmt_data_rsp_msg


class TestVehicleHandler(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        config = Configuration()
        config.anonymized_publishing = False
        saicapi = SaicApi(configuration=SaicApiConfiguration(
            username='aaa@nowhere.org',
            password='xxxxxxxxx'
        ), listener=None)
        publisher = Logger(config)
        vin_info = VinInfo()
        vin_info.vin = VIN
        vin_info.series = 'EH32 S'
        account_prefix = f'/vehicles/{VIN}'
        scheduler = BlockingScheduler()
        vehicle_state = VehicleState(publisher, scheduler, account_prefix, vin_info)
        self.vehicle_handler = VehicleHandler(config, saicapi, publisher, vin_info, vehicle_state)

    @patch.object(SaicApi, 'get_vehicle_status')
    async def test_update_vehicle_status(self, mocked_vehicle_status):
        mock_vehicle_status(mocked_vehicle_status)
        await self.vehicle_handler.update_vehicle_status()

        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_RUNNING), DRIVETRAIN_RUNNING)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_CHARGING), DRIVETRAIN_CHARGING)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_AUXILIARY_BATTERY_VOLTAGE),
                               DRIVETRAIN_AUXILIARY_BATTERY_VOLTAGE)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_MILEAGE), DRIVETRAIN_MILEAGE)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.CLIMATE_INTERIOR_TEMPERATURE),
                               CLIMATE_INTERIOR_TEMPERATURE)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.CLIMATE_EXTERIOR_TEMPERATURE),
                               CLIMATE_EXTERIOR_TEMPERATURE)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE),
                               'on')
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.CLIMATE_BACK_WINDOW_HEAT),
                               'on')
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
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.LIGHTS_SIDE), LIGHTS_SIDE)
        expected_topics = {
            '/vehicles/vin10000000000000/drivetrain/hvBatteryActive',
            '/vehicles/vin10000000000000/refresh/lastActivity',
            '/vehicles/vin10000000000000/drivetrain/running',
            '/vehicles/vin10000000000000/drivetrain/charging',
            '/vehicles/vin10000000000000/climate/interiorTemperature',
            '/vehicles/vin10000000000000/climate/exteriorTemperature',
            '/vehicles/vin10000000000000/drivetrain/auxiliaryBatteryVoltage',
            '/vehicles/vin10000000000000/location/heading',
            '/vehicles/vin10000000000000/location/latitude',
            '/vehicles/vin10000000000000/location/longitude',
            '/vehicles/vin10000000000000/location/elevation',
            '/vehicles/vin10000000000000/location/position',
            '/vehicles/vin10000000000000/location/speed',
            '/vehicles/vin10000000000000/windows/driver',
            '/vehicles/vin10000000000000/windows/passenger',
            '/vehicles/vin10000000000000/windows/rearLeft',
            '/vehicles/vin10000000000000/windows/rearRight',
            '/vehicles/vin10000000000000/windows/sunRoof',
            '/vehicles/vin10000000000000/doors/locked',
            '/vehicles/vin10000000000000/doors/driver',
            '/vehicles/vin10000000000000/doors/passenger',
            '/vehicles/vin10000000000000/doors/rearLeft',
            '/vehicles/vin10000000000000/doors/rearRight',
            '/vehicles/vin10000000000000/doors/bonnet',
            '/vehicles/vin10000000000000/doors/boot',
            '/vehicles/vin10000000000000/tyres/frontLeftPressure',
            '/vehicles/vin10000000000000/tyres/frontRightPressure',
            '/vehicles/vin10000000000000/tyres/rearLeftPressure',
            '/vehicles/vin10000000000000/tyres/rearRightPressure',
            '/vehicles/vin10000000000000/lights/mainBeam',
            '/vehicles/vin10000000000000/lights/dippedBeam',
            '/vehicles/vin10000000000000/lights/side',
            '/vehicles/vin10000000000000/climate/remoteClimateState',
            '/vehicles/vin10000000000000/climate/rearWindowDefrosterHeating',
            '/vehicles/vin10000000000000/climate/heatedSeatsFrontLeftLevel',
            '/vehicles/vin10000000000000/climate/heatedSeatsFrontRightLevel',
            '/vehicles/vin10000000000000/drivetrain/mileage',
            '/vehicles/vin10000000000000/refresh/lastVehicleState'
        }
        self.assertSetEqual(expected_topics, set(self.vehicle_handler.publisher.map.keys()))

    @patch.object(SaicApi, 'get_vehicle_charging_management_data')
    async def test_update_charge_status(self, mocked_charge_status):
        mock_charge_status(mocked_charge_status)
        await self.vehicle_handler.update_charge_status()

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
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_REMAINING_CHARGING_TIME),
                               DRIVETRAIN_REMAINING_CHARGING_TIME)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_LAST_CHARGE_ENDING_POWER),
                               DRIVETRAIN_LAST_CHARGE_ENDING_POWER)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_TOTAL_BATTERY_CAPACITY),
                               REAL_TOTAL_BATTERY_CAPACITY)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_HYBRID_ELECTRICAL_RANGE),
                               DRIVETRAIN_HYBRID_ELECTRICAL_RANGE)
        self.assert_mqtt_topic(TestVehicleHandler.get_topic(mqtt_topics.DRIVETRAIN_CHARGING_CABLE_LOCK),
                               DRIVETRAIN_CHARGING_CABLE_LOCK)
        self.assertEqual(19, len(self.vehicle_handler.publisher.map))

    def assert_mqtt_topic(self, topic: str, value):
        mqtt_map = self.vehicle_handler.publisher.map
        if topic in mqtt_map:
            if isinstance(value, float) or isinstance(mqtt_map[topic], float):
                self.assertAlmostEqual(value, mqtt_map[topic], delta=1)
            else:
                self.assertEqual(value, mqtt_map[topic])
        else:
            self.fail(f'MQTT map does not contain topic {topic}')

    @staticmethod
    def get_topic(sub_topic: str) -> str:
        return f'/vehicles/{VIN}/{sub_topic}'
