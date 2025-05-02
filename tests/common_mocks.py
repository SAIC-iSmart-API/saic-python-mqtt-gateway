from __future__ import annotations

import time

from saic_ismart_client_ng.api.schema import GpsPosition, GpsStatus
from saic_ismart_client_ng.api.vehicle import VehicleStatusResp
from saic_ismart_client_ng.api.vehicle.schema import BasicVehicleStatus
from saic_ismart_client_ng.api.vehicle_charging import ChrgMgmtDataResp
from saic_ismart_client_ng.api.vehicle_charging.schema import (
    ChrgMgmtData,
    RvsChargeStatus,
)

VIN = "vin10000000000000"

DRIVETRAIN_RUNNING = True
DRIVETRAIN_CHARGING = True
DRIVETRAIN_AUXILIARY_BATTERY_VOLTAGE = 42
DRIVETRAIN_MILEAGE = 4000
DRIVETRAIN_RANGE_BMS = 250
DRIVETRAIN_RANGE_VEHICLE = 350
DRIVETRAIN_CURRENT = -42
DRIVETRAIN_VOLTAGE = 42
DRIVETRAIN_POWER = -1.764
DRIVETRAIN_SOC_BMS = 96.3
DRIVETRAIN_SOC_VEHICLE = 48
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
BATTERY_CAPACITY_CORRECTION_FACTOR = (
    REAL_TOTAL_BATTERY_CAPACITY / RAW_TOTAL_BATTERY_CAPACITY
)

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
DOORS_PASSENGER = True
DOORS_REAR_LEFT = False
DOORS_REAR_RIGHT = False
DOORS_BONNET = True
DOORS_BOOT = False

TYRES_FRONT_LEFT_PRESSURE = 2.8
TYRES_FRONT_RIGHT_PRESSURE = 2.8
TYRES_REAR_LEFT_PRESSURE = 2.8
TYRES_REAR_RIGHT_PRESSURE = 2.8

LIGHTS_MAIN_BEAM = False
LIGHTS_DIPPED_BEAM = False
LIGHTS_SIDE = False

BMS_CHARGE_STATUS = "CHARGING_1"


def get_mock_vehicle_status_resp() -> VehicleStatusResp:
    return VehicleStatusResp(
        statusTime=int(time.time()),
        basicVehicleStatus=BasicVehicleStatus(
            engineStatus=1 if DRIVETRAIN_RUNNING else 0,
            extendedData1=DRIVETRAIN_SOC_VEHICLE,
            extendedData2=1 if DRIVETRAIN_CHARGING else 0,
            batteryVoltage=DRIVETRAIN_AUXILIARY_BATTERY_VOLTAGE * 10,
            mileage=DRIVETRAIN_MILEAGE * 10,
            fuelRangeElec=DRIVETRAIN_RANGE_VEHICLE * 10,
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
            bonnetStatus=DOORS_BONNET,
            frontLeftTyrePressure=int(TYRES_FRONT_LEFT_PRESSURE * 25),
            frontRightTyrePressure=int(TYRES_FRONT_RIGHT_PRESSURE * 25),
            rearLeftTyrePressure=int(TYRES_REAR_LEFT_PRESSURE * 25),
            rearRightTyrePressure=int(TYRES_REAR_RIGHT_PRESSURE * 25),
            mainBeamStatus=LIGHTS_MAIN_BEAM,
            dippedBeamStatus=LIGHTS_DIPPED_BEAM,
            sideLightStatus=LIGHTS_SIDE,
            frontLeftSeatHeatLevel=0,
            frontRightSeatHeatLevel=1,
        ),
        gpsPosition=GpsPosition(
            gpsStatus=GpsStatus.FIX_3d.value,
            timeStamp=42,
            wayPoint=GpsPosition.WayPoint(
                position=GpsPosition.WayPoint.Position(
                    latitude=int(LOCATION_LATITUDE * 1000000),
                    longitude=int(LOCATION_LONGITUDE * 1000000),
                    altitude=LOCATION_ELEVATION,
                ),
                heading=LOCATION_HEADING,
                hdop=0,
                satellites=3,
                speed=20,
            ),
        ),
    )


def get_mock_charge_management_data_resp() -> ChrgMgmtDataResp:
    return ChrgMgmtDataResp(
        chrgMgmtData=ChrgMgmtData(
            bmsPackCrntV=0,
            bmsPackCrnt=int((DRIVETRAIN_CURRENT + 1000.0) * 20),
            bmsPackVol=DRIVETRAIN_VOLTAGE * 4,
            bmsPackSOCDsp=int(DRIVETRAIN_SOC_BMS * 10.0),
            bmsEstdElecRng=int(DRIVETRAIN_HYBRID_ELECTRICAL_RANGE * 10.0),
            ccuEleccLckCtrlDspCmd=1,
            bmsChrgSts=1 if DRIVETRAIN_CHARGING else 0,
        ),
        rvsChargeStatus=RvsChargeStatus(
            mileageOfDay=int(DRIVETRAIN_MILEAGE_OF_DAY * 10.0),
            mileageSinceLastCharge=int(DRIVETRAIN_MILEAGE_SINCE_LAST_CHARGE * 10.0),
            realtimePower=int(
                (DRIVETRAIN_SOC_KWH / BATTERY_CAPACITY_CORRECTION_FACTOR) * 10
            ),
            chargingType=DRIVETRAIN_CHARGING_TYPE,
            chargingGunState=DRIVETRAIN_CHARGER_CONNECTED,
            lastChargeEndingPower=int(
                (
                    DRIVETRAIN_LAST_CHARGE_ENDING_POWER
                    / BATTERY_CAPACITY_CORRECTION_FACTOR
                )
                * 10.0
            ),
            totalBatteryCapacity=int(RAW_TOTAL_BATTERY_CAPACITY * 10.0),
            fuelRangeElec=int(DRIVETRAIN_RANGE_BMS * 10.0),
        ),
    )
