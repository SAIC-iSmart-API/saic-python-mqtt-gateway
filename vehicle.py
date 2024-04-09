import datetime
import json
import logging
import math
import os
from dataclasses import asdict
from enum import Enum
from typing import Optional

from apscheduler.job import Job
from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.cron import CronTrigger
from saic_ismart_client_ng.api.message.schema import MessageEntity
from saic_ismart_client_ng.api.schema import GpsStatus
from saic_ismart_client_ng.api.vehicle import VehicleStatusResp
from saic_ismart_client_ng.api.vehicle.schema import VinInfo
from saic_ismart_client_ng.api.vehicle_charging import ChrgMgmtDataResp, TargetBatteryCode, ChargeCurrentLimitCode, \
    ScheduledChargingMode, ScheduledBatteryHeatingResp
from saic_ismart_client_ng.api.vehicle_charging.schema import ChrgMgmtData

import mqtt_topics
from integrations.openwb.charging_station import ChargingStation
from exceptions import MqttGatewayException
from publisher.core import Publisher
from utils import value_in_range, is_valid_temperature

DEFAULT_AC_TEMP = 22
PRESSURE_TO_BAR_FACTOR = 0.04

LOG = logging.getLogger(__name__)
LOG.setLevel(level=os.getenv('LOG_LEVEL', 'INFO').upper())


class RefreshMode(Enum):
    FORCE = 'force'
    OFF = 'off'
    PERIODIC = 'periodic'

    @staticmethod
    def get(mode: str):
        return RefreshMode[mode.upper()]


class VehicleState:
    def __init__(
            self,
            publisher: Publisher,
            scheduler: BaseScheduler,
            account_prefix: str,
            vin: VinInfo,
            charging_station: Optional[ChargingStation] = None,
            charge_polling_min_percent: float = 1.0,
            total_battery_capacity: Optional[float] = None,
    ):
        self.publisher = publisher
        self.vin = vin.vin
        self.series = str(vin.series).strip().upper()
        self.model = str(vin.modelName).strip().upper()
        self.mqtt_vin_prefix = f'{account_prefix}'
        self.charging_station = charging_station
        self.last_car_activity = datetime.datetime.min
        self.last_successful_refresh = datetime.datetime.min
        self.__last_failed_refresh: datetime.datetime | None = None
        self.__failed_refresh_counter = 0
        self.__refresh_period_error = 30
        self.last_car_shutdown = datetime.datetime.now()
        self.last_car_vehicle_message = datetime.datetime.min
        # treat high voltage battery as active, if we don't have any other information
        self.hv_battery_active = True
        self.is_charging = False
        self.refresh_period_active = -1
        self.refresh_period_inactive = -1
        self.refresh_period_after_shutdown = -1
        self.refresh_period_inactive_grace = -1
        self.target_soc: Optional[TargetBatteryCode] = None
        self.charge_current_limit: Optional[ChargeCurrentLimitCode] = None
        self.refresh_period_charging = 0
        self.charge_polling_min_percent = charge_polling_min_percent
        self.refresh_mode = RefreshMode.OFF
        self.previous_refresh_mode = RefreshMode.OFF
        self.properties = {}
        self.__remote_ac_temp: Optional[int] = None
        self.__remote_ac_running: bool = False
        self.__remote_heated_seats_front_left_level: int = 0
        self.__remote_heated_seats_front_right_level: int = 0
        self.__scheduler = scheduler
        self.__total_battery_capacity = total_battery_capacity
        self.__scheduled_battery_heating_enabled = False
        self.__scheduled_battery_heating_start = None

    def set_refresh_period_active(self, seconds: int):
        self.publisher.publish_int(self.get_topic(mqtt_topics.REFRESH_PERIOD_ACTIVE), seconds)
        human_readable_period = str(datetime.timedelta(seconds=seconds))
        LOG.info(f'Setting active query interval in vehicle handler for VIN {self.vin} to {human_readable_period}')
        self.refresh_period_active = seconds
        # Recompute charging refresh period, if active refresh period is changed
        self.set_refresh_period_charging(self.refresh_period_charging)

    def set_refresh_period_inactive(self, seconds: int):
        self.publisher.publish_int(self.get_topic(mqtt_topics.REFRESH_PERIOD_INACTIVE), seconds)
        human_readable_period = str(datetime.timedelta(seconds=seconds))
        LOG.info(f'Setting inactive query interval in vehicle handler for VIN {self.vin} to {human_readable_period}')
        self.refresh_period_inactive = seconds
        # Recompute charging refresh period, if inactive refresh period is changed
        self.set_refresh_period_charging(self.refresh_period_charging)

    def set_refresh_period_charging(self, seconds: int):
        # Do not refresh more than the active period and less than the inactive one
        seconds = round(seconds)
        seconds = min(max(seconds, self.refresh_period_active), self.refresh_period_inactive) if seconds > 0 else 0
        self.publisher.publish_int(self.get_topic(mqtt_topics.REFRESH_PERIOD_CHARGING), seconds)
        human_readable_period = str(datetime.timedelta(seconds=seconds))
        LOG.info(f'Setting charging query interval in vehicle handler for VIN {self.vin} to {human_readable_period}')
        self.refresh_period_charging = seconds

    def set_refresh_period_after_shutdown(self, seconds: int):
        self.publisher.publish_int(self.get_topic(mqtt_topics.REFRESH_PERIOD_AFTER_SHUTDOWN), seconds)
        human_readable_period = str(datetime.timedelta(seconds=seconds))
        LOG.info(
            f'Setting after shutdown query interval in vehicle handler for VIN {self.vin} to {human_readable_period}'
        )
        self.refresh_period_after_shutdown = seconds

    def set_refresh_period_inactive_grace(self, refresh_period_inactive_grace: int):
        if (
                self.refresh_period_inactive_grace == -1
                or self.refresh_period_inactive_grace != refresh_period_inactive_grace
        ):
            self.publisher.publish_int(self.get_topic(mqtt_topics.REFRESH_PERIOD_INACTIVE_GRACE),
                                       refresh_period_inactive_grace)
            self.refresh_period_inactive_grace = refresh_period_inactive_grace

    def update_target_soc(self, target_soc: TargetBatteryCode):
        if self.target_soc != target_soc and target_soc is not None:
            self.publisher.publish_int(self.get_topic(mqtt_topics.DRIVETRAIN_SOC_TARGET), target_soc.percentage)
            self.target_soc = target_soc

    def update_charge_current_limit(self, charge_current_limit: ChargeCurrentLimitCode):
        if self.charge_current_limit != charge_current_limit and charge_current_limit is not None:
            try:
                self.publisher.publish_str(
                    self.get_topic(mqtt_topics.DRIVETRAIN_CHARGECURRENT_LIMIT),
                    charge_current_limit.limit
                )
                self.charge_current_limit = charge_current_limit
            except ValueError:
                LOG.exception(f'Unhandled charge current limit {charge_current_limit}')

    def update_scheduled_charging(
            self,
            start_time: datetime.time,
            mode: ScheduledChargingMode
    ):
        scheduled_charging_job_id = f'{self.vin}_scheduled_charging'
        existing_job: Job | None = self.__scheduler.get_job(scheduled_charging_job_id)
        if mode in [ScheduledChargingMode.UNTIL_CONFIGURED_TIME, ScheduledChargingMode.UNTIL_CONFIGURED_SOC]:
            if self.refresh_period_inactive_grace > 0:
                # Add a grace period to the start time, so that the car is not woken up too early
                dt = (datetime.datetime.now()
                      .replace(hour=start_time.hour, minute=start_time.minute, second=0, microsecond=0)
                      + datetime.timedelta(seconds=self.refresh_period_inactive_grace))
                start_time = dt.time()
            trigger = CronTrigger.from_crontab(f'{start_time.minute} {start_time.hour} * * *')
            if existing_job is not None:
                existing_job.reschedule(trigger=trigger)
                LOG.info(f'Rescheduled check for charging start for VIN {self.vin} at {start_time}')
            else:
                self.__scheduler.add_job(
                    func=self.set_refresh_mode,
                    args=[RefreshMode.FORCE],
                    trigger=trigger,
                    kwargs={},
                    name=scheduled_charging_job_id,
                    id=scheduled_charging_job_id,
                    replace_existing=True,
                )
                LOG.info(f'Scheduled check for charging start for VIN {self.vin} at {start_time}')
        elif existing_job is not None:
            existing_job.remove()
            LOG.info(f'Removed scheduled check for charging start for VIN {self.vin}')

    def is_complete(self) -> bool:
        return self.refresh_period_active != -1 \
            and self.refresh_period_inactive != -1 \
            and self.refresh_period_after_shutdown != -1 \
            and self.refresh_period_inactive_grace != -1 \
            and self.refresh_mode

    def set_is_charging(self, is_charging: bool):
        self.is_charging = is_charging
        self.set_hv_battery_active(self.is_charging)
        self.publisher.publish_bool(self.get_topic(mqtt_topics.DRIVETRAIN_CHARGING), self.is_charging)

    def handle_vehicle_status(self, vehicle_status: VehicleStatusResp) -> None:
        is_engine_running = vehicle_status.is_engine_running
        self.is_charging = vehicle_status.is_charging
        basic_vehicle_status = vehicle_status.basicVehicleStatus
        remote_climate_status = basic_vehicle_status.remoteClimateStatus or 0
        rear_window_heat_state = basic_vehicle_status.rmtHtdRrWndSt or 0

        hv_battery_active = (
                self.is_charging
                or is_engine_running
                or remote_climate_status > 0
                or rear_window_heat_state > 0
        )

        self.set_hv_battery_active(hv_battery_active)

        self.publisher.publish_bool(self.get_topic(mqtt_topics.DRIVETRAIN_RUNNING), is_engine_running)
        self.publisher.publish_bool(self.get_topic(mqtt_topics.DRIVETRAIN_CHARGING), self.is_charging)
        interior_temperature = basic_vehicle_status.interiorTemperature
        if is_valid_temperature(interior_temperature):
            self.publisher.publish_int(self.get_topic(mqtt_topics.CLIMATE_INTERIOR_TEMPERATURE), interior_temperature)
        exterior_temperature = basic_vehicle_status.exteriorTemperature
        if is_valid_temperature(exterior_temperature):
            self.publisher.publish_int(self.get_topic(mqtt_topics.CLIMATE_EXTERIOR_TEMPERATURE), exterior_temperature)
        battery_voltage = basic_vehicle_status.batteryVoltage
        if value_in_range(battery_voltage, 1, 65535):
            self.publisher.publish_float(self.get_topic(mqtt_topics.DRIVETRAIN_AUXILIARY_BATTERY_VOLTAGE),
                                         battery_voltage / 10.0)

        speed = None
        gps_position = vehicle_status.gpsPosition
        if (
                gps_position
                and gps_position.gps_status_decoded in [GpsStatus.FIX_2D, GpsStatus.FIX_3d]
        ):
            way_point = gps_position.wayPoint
            if way_point:
                speed = way_point.speed / 10.0
                self.publisher.publish_int(self.get_topic(mqtt_topics.LOCATION_HEADING), way_point.heading)
                position = way_point.position
                if position:
                    if gps_position.gps_status_decoded == GpsStatus.FIX_3d:
                        self.publisher.publish_int(self.get_topic(mqtt_topics.LOCATION_ELEVATION), position.altitude)
                    latitude = position.latitude / 1000000.0
                    longitude = position.longitude / 1000000.0
                    if abs(latitude) <= 90 and abs(longitude) <= 180:
                        self.publisher.publish_float(self.get_topic(mqtt_topics.LOCATION_LATITUDE), latitude)
                        self.publisher.publish_float(self.get_topic(mqtt_topics.LOCATION_LONGITUDE), longitude)
                        self.publisher.publish_json(self.get_topic(mqtt_topics.LOCATION_POSITION), {
                            'latitude': latitude,
                            'longitude': longitude,
                        })

        # Assume speed is 0 if the vehicle is parked and we have no other info
        if speed is None and vehicle_status.is_parked:
            speed = 0.0

        if speed is not None:
            self.publisher.publish_float(self.get_topic(mqtt_topics.LOCATION_SPEED), speed)

        if basic_vehicle_status.driverWindow is not None:
            self.publisher.publish_bool(self.get_topic(mqtt_topics.WINDOWS_DRIVER), basic_vehicle_status.driverWindow)
        if basic_vehicle_status.passengerWindow is not None:
            self.publisher.publish_bool(self.get_topic(mqtt_topics.WINDOWS_PASSENGER),
                                        basic_vehicle_status.passengerWindow)
        if basic_vehicle_status.rearLeftWindow is not None:
            self.publisher.publish_bool(self.get_topic(mqtt_topics.WINDOWS_REAR_LEFT),
                                        basic_vehicle_status.rearLeftWindow)
        if basic_vehicle_status.rearRightWindow is not None:
            self.publisher.publish_bool(self.get_topic(mqtt_topics.WINDOWS_REAR_RIGHT),
                                        basic_vehicle_status.rearRightWindow)
        if basic_vehicle_status.sunroofStatus is not None:
            self.publisher.publish_bool(self.get_topic(mqtt_topics.WINDOWS_SUN_ROOF),
                                        basic_vehicle_status.sunroofStatus)

        self.publisher.publish_bool(self.get_topic(mqtt_topics.DOORS_LOCKED), basic_vehicle_status.lockStatus)
        self.publisher.publish_bool(self.get_topic(mqtt_topics.DOORS_DRIVER), basic_vehicle_status.driverDoor)
        self.publisher.publish_bool(self.get_topic(mqtt_topics.DOORS_PASSENGER), basic_vehicle_status.passengerDoor)
        self.publisher.publish_bool(self.get_topic(mqtt_topics.DOORS_REAR_LEFT), basic_vehicle_status.rearLeftDoor)
        self.publisher.publish_bool(self.get_topic(mqtt_topics.DOORS_REAR_RIGHT), basic_vehicle_status.rearRightDoor)
        self.publisher.publish_bool(self.get_topic(mqtt_topics.DOORS_BONNET), basic_vehicle_status.bonnetStatus)
        self.publisher.publish_bool(self.get_topic(mqtt_topics.DOORS_BOOT), basic_vehicle_status.bootStatus)

        self.__publish_tyre(basic_vehicle_status.frontLeftTyrePressure, mqtt_topics.TYRES_FRONT_LEFT_PRESSURE)
        self.__publish_tyre(basic_vehicle_status.frontRightTyrePressure, mqtt_topics.TYRES_FRONT_RIGHT_PRESSURE)
        self.__publish_tyre(basic_vehicle_status.rearLeftTyrePressure, mqtt_topics.TYRES_REAR_LEFT_PRESSURE)
        self.__publish_tyre(basic_vehicle_status.rearRightTyrePressure, mqtt_topics.TYRES_REAR_RIGHT_PRESSURE)

        self.publisher.publish_bool(self.get_topic(mqtt_topics.LIGHTS_MAIN_BEAM), basic_vehicle_status.mainBeamStatus)
        self.publisher.publish_bool(self.get_topic(mqtt_topics.LIGHTS_DIPPED_BEAM),
                                    basic_vehicle_status.dippedBeamStatus)
        self.publisher.publish_bool(self.get_topic(mqtt_topics.LIGHTS_SIDE), basic_vehicle_status.sideLightStatus)

        self.publisher.publish_str(self.get_topic(mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE),
                                   VehicleState.to_remote_climate(remote_climate_status))
        self.__remote_ac_running = remote_climate_status == 2

        self.publisher.publish_str(self.get_topic(mqtt_topics.CLIMATE_BACK_WINDOW_HEAT),
                                   'off' if rear_window_heat_state == 0 else 'on')

        if value_in_range(basic_vehicle_status.frontLeftSeatHeatLevel, 0, 255):
            self.__remote_heated_seats_front_left_level = basic_vehicle_status.frontLeftSeatHeatLevel
            self.publisher.publish_int(self.get_topic(mqtt_topics.CLIMATE_HEATED_SEATS_FRONT_LEFT_LEVEL),
                                       self.__remote_heated_seats_front_left_level)

        if value_in_range(basic_vehicle_status.frontRightSeatHeatLevel, 0, 255):
            self.__remote_heated_seats_front_right_level = basic_vehicle_status.frontRightSeatHeatLevel
            self.publisher.publish_int(self.get_topic(mqtt_topics.CLIMATE_HEATED_SEATS_FRONT_RIGHT_LEVEL),
                                       self.__remote_heated_seats_front_right_level)

        if value_in_range(basic_vehicle_status.mileage, 1, 2147483647):
            mileage = basic_vehicle_status.mileage / 10.0
            self.publisher.publish_float(self.get_topic(mqtt_topics.DRIVETRAIN_MILEAGE), mileage)

        if (
                basic_vehicle_status.currentJourneyId is not None
                and basic_vehicle_status.currentJourneyDistance is not None
        ):
            self.publisher.publish_json(self.get_topic(mqtt_topics.DRIVETRAIN_CURRENT_JOURNEY), {
                'id': basic_vehicle_status.currentJourneyId,
                'distance': round(basic_vehicle_status.currentJourneyDistance / 10.0, 1)
            })

        self.publisher.publish_str(self.get_topic(mqtt_topics.REFRESH_LAST_VEHICLE_STATE),
                                   VehicleState.datetime_to_str(datetime.datetime.now()))

    def __publish_tyre(self, raw_value: int, topic: str):
        if value_in_range(raw_value, 1, 255):
            bar_value = raw_value * PRESSURE_TO_BAR_FACTOR
            self.publisher.publish_float(self.get_topic(topic), round(bar_value, 2))

    def set_hv_battery_active(self, hv_battery_active: bool):
        if (
                not hv_battery_active
                and self.hv_battery_active
        ):
            self.last_car_shutdown = datetime.datetime.now()

        self.hv_battery_active = hv_battery_active
        self.publisher.publish_bool(self.get_topic(mqtt_topics.DRIVETRAIN_HV_BATTERY_ACTIVE), hv_battery_active)

        if hv_battery_active:
            self.notify_car_activity_time(datetime.datetime.now(), True)

    def notify_car_activity_time(self, now: datetime.datetime, force: bool):
        if (
                self.last_car_activity == datetime.datetime.min
                or force
                or self.last_car_activity < now
        ):
            self.last_car_activity = datetime.datetime.now()
            self.publisher.publish_str(self.get_topic(mqtt_topics.REFRESH_LAST_ACTIVITY),
                                       VehicleState.datetime_to_str(self.last_car_activity))

    def notify_message(self, message: MessageEntity):
        if (
                self.last_car_vehicle_message == datetime.datetime.min
                or message.message_time > self.last_car_vehicle_message
        ):
            self.last_car_vehicle_message = message.message_time
            self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_LAST_MESSAGE_ID), str(message.messageId))
            self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_LAST_MESSAGE_TYPE), message.messageType)
            self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_LAST_MESSAGE_TITLE), message.title)
            self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_LAST_MESSAGE_TIME),
                                       VehicleState.datetime_to_str(self.last_car_vehicle_message))
            self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_LAST_MESSAGE_SENDER), message.sender)
            if message.content:
                self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_LAST_MESSAGE_CONTENT), message.content)
            self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_LAST_MESSAGE_STATUS), message.read_status)
            if message.vin:
                self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_LAST_MESSAGE_VIN), message.vin)
                self.notify_car_activity_time(message.message_time, True)

    def should_refresh(self) -> bool:
        match self.refresh_mode:
            case RefreshMode.OFF:
                return False
            case RefreshMode.FORCE:
                self.set_refresh_mode(self.previous_refresh_mode)
                return True
            # RefreshMode.PERIODIC is treated like default
            case _:
                if self.last_successful_refresh is None:
                    self.mark_successful_refresh()
                    return True

                last_actual_poll = self.last_successful_refresh
                if self.last_failed_refresh is not None:
                    last_actual_poll = max(last_actual_poll, self.last_failed_refresh)

                # Try refreshing even if we last failed as long as the last_car_activity is newer
                if self.last_car_activity > last_actual_poll:
                    return True

                if self.last_failed_refresh is not None:
                    result = self.last_failed_refresh < datetime.datetime.now() - datetime.timedelta(
                        seconds=float(self.refresh_period_error)
                    )
                    LOG.debug(f'Gateway failed refresh previously. Should refresh: {result}')
                    return result

                if self.is_charging and self.refresh_period_charging > 0:
                    result = self.last_successful_refresh < datetime.datetime.now() - datetime.timedelta(
                        seconds=float(self.refresh_period_charging)
                    )
                    LOG.debug(f'HV battery is charging. Should refresh: {result}')
                    return result

                if self.hv_battery_active:
                    result = self.last_successful_refresh < datetime.datetime.now() - datetime.timedelta(
                        seconds=float(self.refresh_period_active)
                    )
                    LOG.debug(f'HV battery is active. Should refresh: {result}')
                    return result

                last_shutdown_plus_refresh = self.last_car_shutdown + datetime.timedelta(
                    seconds=float(self.refresh_period_inactive_grace)
                )
                if last_shutdown_plus_refresh > datetime.datetime.now():
                    result = self.last_successful_refresh < datetime.datetime.now() - datetime.timedelta(
                        seconds=float(self.refresh_period_after_shutdown))
                    LOG.debug(f'Refresh grace period after shutdown has not passed. Should refresh: {result}')
                    return result

                result = self.last_successful_refresh < datetime.datetime.now() - datetime.timedelta(
                    seconds=float(self.refresh_period_inactive)
                )
                LOG.debug(
                    f'HV battery is inactive and refresh period after shutdown is over. Should refresh: {result}'
                )
                return result

    def mark_successful_refresh(self):
        self.last_successful_refresh = datetime.datetime.now()
        self.last_failed_refresh = None
        self.publisher.publish_str(self.get_topic(mqtt_topics.AVAILABLE), 'online')

    def mark_failed_refresh(self):
        self.last_failed_refresh = datetime.datetime.now()
        self.publisher.publish_str(self.get_topic(mqtt_topics.AVAILABLE), 'offline')

    @property
    def refresh_period_error(self):
        return self.__refresh_period_error

    @property
    def last_failed_refresh(self):
        return self.__last_failed_refresh

    @last_failed_refresh.setter
    def last_failed_refresh(self, value: datetime.datetime | None):
        self.__last_failed_refresh = value
        if value is None:
            self.__failed_refresh_counter = 0
            self.__refresh_period_error = 30
        else:
            self.__refresh_period_error = round(min(30 + 0.5 * ((2 ** self.__failed_refresh_counter) - 1), 3600))
            self.__failed_refresh_counter = self.__failed_refresh_counter + 1
            self.publisher.publish_str(
                self.get_topic(mqtt_topics.REFRESH_LAST_ERROR),
                VehicleState.datetime_to_str(value)
            )
        self.publisher.publish_int(self.get_topic(mqtt_topics.REFRESH_PERIOD_ERROR), self.__refresh_period_error)

    def configure(self, vin_info: VinInfo):
        self.publisher.publish_str(
            self.get_topic(mqtt_topics.INTERNAL_CONFIGURATION_RAW),
            json.dumps([asdict(x) for x in vin_info.vehicleModelConfiguration])
        )
        self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_BRAND), vin_info.brandName)
        self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_MODEL), vin_info.modelName)
        self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_YEAR), vin_info.modelYear)
        self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_SERIES), vin_info.series)
        if vin_info.colorName:
            self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_COLOR), vin_info.colorName)
        self.properties = {}
        for c in vin_info.vehicleModelConfiguration:
            property_name = c.itemName
            property_code = c.itemCode
            property_value = c.itemValue
            property_code_topic = f'{mqtt_topics.INFO_CONFIGURATION}/{property_code}'
            property_name_topic = f'{mqtt_topics.INFO_CONFIGURATION}/{property_name}'
            self.properties[property_name] = {'code': property_code, 'value': property_value}
            self.properties[property_code] = {'name': property_name, 'value': property_value}
            self.publisher.publish_str(self.get_topic(property_code_topic), property_value)
            self.publisher.publish_str(self.get_topic(property_name_topic), property_value)

    def configure_missing(self):
        if self.refresh_period_active == -1:
            self.set_refresh_period_active(30)
        if self.refresh_period_after_shutdown == -1:
            self.set_refresh_period_after_shutdown(120)
        if self.refresh_period_inactive == -1:
            # in seconds (Once a day to protect your 12V battery)
            self.set_refresh_period_inactive(86400)
        if self.refresh_period_inactive_grace == -1:
            self.set_refresh_period_inactive_grace(600)
        if self.__remote_ac_temp is None:
            self.set_ac_temperature(DEFAULT_AC_TEMP)
        # Make sure the only refresh mode that is not supported at start is RefreshMode.PERIODIC
        if self.refresh_mode in [RefreshMode.OFF, RefreshMode.FORCE]:
            self.set_refresh_mode(RefreshMode.PERIODIC)

    async def configure_by_message(self, *, topic: str, payload: str):
        payload = payload.lower()
        match topic:
            case mqtt_topics.REFRESH_MODE:
                try:
                    refresh_mode = RefreshMode.get(payload)
                    self.set_refresh_mode(refresh_mode)
                except KeyError:
                    raise MqttGatewayException(f'Unsupported payload {payload}')
            case mqtt_topics.REFRESH_PERIOD_ACTIVE:
                try:
                    seconds = int(payload)
                    self.set_refresh_period_active(seconds)
                except ValueError:
                    raise MqttGatewayException(f'Error setting value for payload {payload}')
            case mqtt_topics.REFRESH_PERIOD_INACTIVE:
                try:
                    seconds = int(payload)
                    self.set_refresh_period_inactive(seconds)
                except ValueError:
                    raise MqttGatewayException(f'Error setting value for payload {payload}')
            case mqtt_topics.REFRESH_PERIOD_AFTER_SHUTDOWN:
                try:
                    seconds = int(payload)
                    self.set_refresh_period_after_shutdown(seconds)
                except ValueError:
                    raise MqttGatewayException(f'Error setting value for payload {payload}')
            case mqtt_topics.REFRESH_PERIOD_INACTIVE_GRACE:
                try:
                    seconds = int(payload)
                    self.set_refresh_period_inactive_grace(seconds)
                except ValueError:
                    raise MqttGatewayException(f'Error setting value for payload {payload}')
            case _:
                raise MqttGatewayException(f'Unsupported topic {topic}')

    def handle_charge_status(self, charge_info_resp: ChrgMgmtDataResp) -> None:
        charge_mgmt_data = charge_info_resp.chrgMgmtData
        is_valid_current = (
                charge_mgmt_data.bmsPackCrntV == 0
                and value_in_range(charge_mgmt_data.bmsPackCrnt, 0, 65535)
        )
        if is_valid_current:
            self.publisher.publish_float(
                self.get_topic(mqtt_topics.DRIVETRAIN_CURRENT),
                round(charge_mgmt_data.decoded_current, 3)
            )

        is_valid_voltage = value_in_range(charge_mgmt_data.bmsPackVol, 0, 65535)
        if is_valid_voltage:
            self.publisher.publish_float(
                self.get_topic(mqtt_topics.DRIVETRAIN_VOLTAGE),
                round(charge_mgmt_data.decoded_voltage, 3)
            )
        is_valid_power = is_valid_current and is_valid_voltage
        if is_valid_power:
            self.publisher.publish_float(
                self.get_topic(mqtt_topics.DRIVETRAIN_POWER),
                round(charge_mgmt_data.decoded_power, 3)
            )

        obc_voltage = charge_mgmt_data.onBdChrgrAltrCrntInptVol
        if obc_voltage is not None and obc_voltage != 0:
            obc_current = charge_mgmt_data.onBdChrgrAltrCrntInptCrnt
            self.publisher.publish_float(
                self.get_topic(mqtt_topics.OBC_CURRENT),
                round(obc_current / 10.0, 1)
            )
            self.publisher.publish_int(
                self.get_topic(mqtt_topics.OBC_VOLTAGE),
                obc_voltage
            )
        else:
            self.publisher.publish_float(self.get_topic(mqtt_topics.OBC_CURRENT), 0.0)
            self.publisher.publish_int(self.get_topic(mqtt_topics.OBC_VOLTAGE), 0)

        raw_charge_current_limit = charge_mgmt_data.bmsAltngChrgCrntDspCmd
        if (
                raw_charge_current_limit is not None
                and raw_charge_current_limit != 0
        ):
            try:
                self.update_charge_current_limit(ChargeCurrentLimitCode(raw_charge_current_limit))
            except ValueError:
                LOG.warning(f'Invalid charge current limit received: {raw_charge_current_limit}')

        raw_target_soc = charge_mgmt_data.bmsOnBdChrgTrgtSOCDspCmd
        if raw_target_soc is not None:
            try:
                self.update_target_soc(TargetBatteryCode(raw_target_soc))
            except ValueError:
                LOG.warning(f'Invalid target SOC received: {raw_target_soc}')

        soc = charge_mgmt_data.bmsPackSOCDsp / 10.0
        if soc <= 100.0:
            self.publisher.publish_float(self.get_topic(mqtt_topics.DRIVETRAIN_SOC), soc)
            if (
                    self.charging_station
                    and self.charging_station.soc_topic
            ):
                self.publisher.publish_int(self.charging_station.soc_topic, int(soc), True)

        estd_elec_rng = charge_mgmt_data.bmsEstdElecRng
        if value_in_range(estd_elec_rng, 0, 65535) and estd_elec_rng != 2047:
            estimated_electrical_range = estd_elec_rng
            self.publisher.publish_int(
                self.get_topic(mqtt_topics.DRIVETRAIN_HYBRID_ELECTRICAL_RANGE),
                estimated_electrical_range
            )

        bms_chrg_sts = charge_mgmt_data.bmsChrgSts
        if bms_chrg_sts is not None:
            self.publisher.publish_int(self.get_topic(mqtt_topics.BMS_CHARGE_STATUS), bms_chrg_sts)

        charge_status = charge_info_resp.rvsChargeStatus
        fuel_range_elec = charge_status.fuelRangeElec
        if value_in_range(fuel_range_elec, 0, 65535):
            electric_range = fuel_range_elec / 10.0
            self.publisher.publish_float(self.get_topic(mqtt_topics.DRIVETRAIN_RANGE), electric_range)
            if (
                    self.charging_station
                    and self.charging_station.range_topic
            ):
                self.publisher.publish_float(self.charging_station.range_topic, electric_range, True)

        if value_in_range(charge_status.mileageOfDay, 0, 65535):
            mileage_of_the_day = charge_status.mileageOfDay / 10.0
            self.publisher.publish_float(self.get_topic(mqtt_topics.DRIVETRAIN_MILEAGE_OF_DAY), mileage_of_the_day)

        if value_in_range(charge_status.mileageSinceLastCharge, 0, 65535):
            mileage_since_last_charge = charge_status.mileageSinceLastCharge / 10.0
            self.publisher.publish_float(self.get_topic(mqtt_topics.DRIVETRAIN_MILEAGE_SINCE_LAST_CHARGE),
                                         mileage_since_last_charge)

        self.publisher.publish_int(self.get_topic(mqtt_topics.DRIVETRAIN_CHARGING_TYPE), charge_status.chargingType)
        self.publisher.publish_bool(self.get_topic(mqtt_topics.DRIVETRAIN_CHARGER_CONNECTED),
                                    charge_status.chargingGunState)

        if has_scheduled_charging_info(charge_mgmt_data):
            try:
                start_hour = charge_mgmt_data.bmsReserStHourDspCmd
                start_minute = charge_mgmt_data.bmsReserStMintueDspCmd
                start_time = datetime.time(hour=start_hour, minute=start_minute)
                end_hour = charge_mgmt_data.bmsReserSpHourDspCmd
                end_minute = charge_mgmt_data.bmsReserSpMintueDspCmd
                mode = ScheduledChargingMode(charge_mgmt_data.bmsReserCtrlDspCmd)
                self.publisher.publish_json(self.get_topic(mqtt_topics.DRIVETRAIN_CHARGING_SCHEDULE), {
                    'startTime': "{:02d}:{:02d}".format(start_hour, start_minute),
                    'endTime': "{:02d}:{:02d}".format(end_hour, end_minute),
                    'mode': mode.name,
                })
                self.update_scheduled_charging(start_time, mode)

            except ValueError:
                LOG.exception("Error parsing scheduled charging info")

        # Only publish remaining charging time if the car tells us the value is OK
        remaining_charging_time = None
        if charge_mgmt_data.chrgngRmnngTimeV == 0:
            remaining_charging_time = charge_mgmt_data.chrgngRmnngTime * 60
            self.publisher.publish_int(
                self.get_topic(mqtt_topics.DRIVETRAIN_REMAINING_CHARGING_TIME),
                remaining_charging_time
            )
        else:
            self.publisher.publish_int(self.get_topic(mqtt_topics.DRIVETRAIN_REMAINING_CHARGING_TIME), 0)

        charge_status_start_time = charge_status.startTime
        if value_in_range(charge_status_start_time, 1, 2147483647):
            self.publisher.publish_int(
                self.get_topic(mqtt_topics.DRIVETRAIN_CHARGING_LAST_START),
                charge_status_start_time
            )

        charge_status_end_time = charge_status.endTime
        if value_in_range(charge_status_end_time, 1, 2147483647):
            self.publisher.publish_int(
                self.get_topic(mqtt_topics.DRIVETRAIN_CHARGING_LAST_END),
                charge_status_end_time
            )

        self.publisher.publish_str(self.get_topic(mqtt_topics.REFRESH_LAST_CHARGE_STATE),
                                   VehicleState.datetime_to_str(datetime.datetime.now()))

        real_total_battery_capacity = self.get_actual_battery_capacity()
        raw_total_battery_capacity = None

        if (
                charge_status.totalBatteryCapacity is not None
                and charge_status.totalBatteryCapacity > 0
        ):
            raw_total_battery_capacity = charge_status.totalBatteryCapacity / 10.0

        battery_capacity_correction_factor = 1.0
        if real_total_battery_capacity is None and raw_total_battery_capacity is not None:
            LOG.debug(f"Setting real battery capacity to raw battery capacity {raw_total_battery_capacity}")
            real_total_battery_capacity = raw_total_battery_capacity
            battery_capacity_correction_factor = 1.0
        elif real_total_battery_capacity is not None and raw_total_battery_capacity is None:
            LOG.debug(f"Setting raw battery capacity to real battery capacity {real_total_battery_capacity}")
            battery_capacity_correction_factor = 1.0
        elif real_total_battery_capacity is not None and raw_total_battery_capacity is not None:
            LOG.debug(
                f"Calculating full battery capacity correction factor based on "
                f"real={real_total_battery_capacity} and raw={raw_total_battery_capacity}"
            )
            battery_capacity_correction_factor = real_total_battery_capacity / raw_total_battery_capacity
        elif real_total_battery_capacity is None and raw_total_battery_capacity is None:
            LOG.warning("No battery capacity information available")
            battery_capacity_correction_factor = 1.0

        if real_total_battery_capacity is not None and real_total_battery_capacity > 0:
            self.publisher.publish_float(
                self.get_topic(mqtt_topics.DRIVETRAIN_TOTAL_BATTERY_CAPACITY),
                real_total_battery_capacity
            )
        soc_kwh = (battery_capacity_correction_factor * charge_status.realtimePower) / 10.0
        self.publisher.publish_float(self.get_topic(mqtt_topics.DRIVETRAIN_SOC_KWH), round(soc_kwh, 2))

        last_charge_ending_power = charge_status.lastChargeEndingPower
        if value_in_range(last_charge_ending_power, 0, 65535):
            last_charge_ending_power = (battery_capacity_correction_factor * last_charge_ending_power) / 10.0
            self.publisher.publish_float(
                self.get_topic(mqtt_topics.DRIVETRAIN_LAST_CHARGE_ENDING_POWER),
                round(last_charge_ending_power, 2)
            )

        power_usage_of_day = charge_status.powerUsageOfDay
        if value_in_range(power_usage_of_day, 0, 65535):
            power_usage_of_day = (battery_capacity_correction_factor * power_usage_of_day) / 10.0
            self.publisher.publish_float(
                self.get_topic(mqtt_topics.DRIVETRAIN_POWER_USAGE_OF_DAY),
                round(power_usage_of_day, 2)
            )

        power_usage_since_last_charge = charge_status.powerUsageSinceLastCharge
        if value_in_range(power_usage_since_last_charge, 0, 65535):
            power_usage_since_last_charge = (battery_capacity_correction_factor * power_usage_since_last_charge) / 10.0
            self.publisher.publish_float(
                self.get_topic(mqtt_topics.DRIVETRAIN_POWER_USAGE_SINCE_LAST_CHARGE),
                round(power_usage_since_last_charge, 2)
            )

        if (
                charge_status.chargingGunState
                and is_valid_power
                and charge_mgmt_data.decoded_power < -1
        ):
            # Only compute a dynamic refresh period if we have detected at least 1kW of power during charging
            time_for_1pct = 36.0 * self.get_actual_battery_capacity() / abs(charge_mgmt_data.decoded_power)
            time_for_min_pct = math.ceil(self.charge_polling_min_percent * time_for_1pct)
            # It doesn't make sense to refresh less often than the estimated time for completion
            if remaining_charging_time > 0:
                computed_refresh_period = min(remaining_charging_time, time_for_min_pct)
            else:
                computed_refresh_period = time_for_1pct
            self.set_refresh_period_charging(computed_refresh_period)
        elif not self.is_charging:
            # Reset the charging refresh period if we detected we are no longer charging
            self.set_refresh_period_charging(0)
        else:
            # Otherwise let's keep the last computed refresh period
            # This avoids falling back to the active refresh period which, being too often, results in a ban from
            # the SAIC API
            pass

        self.publisher.publish_bool(
            self.get_topic(mqtt_topics.DRIVETRAIN_BATTERY_HEATING),
            charge_mgmt_data.is_battery_heating
        )

        self.publisher.publish_bool(
            self.get_topic(mqtt_topics.DRIVETRAIN_CHARGING_CABLE_LOCK),
            charge_mgmt_data.charging_port_locked
        )

    def handle_scheduled_battery_heating_status(self, scheduled_battery_heating_status: ScheduledBatteryHeatingResp):
        if scheduled_battery_heating_status:
            is_enabled = scheduled_battery_heating_status.status
            if is_enabled:
                start_time = scheduled_battery_heating_status.decoded_start_time
            else:
                start_time = self.__scheduled_battery_heating_start
        else:
            start_time = self.__scheduled_battery_heating_start
            is_enabled = False

        self.update_scheduled_battery_heating(
            start_time,
            is_enabled
        )

    def update_scheduled_battery_heating(self, start_time: datetime.time, enabled: bool):
        changed = False
        if self.__scheduled_battery_heating_start != start_time:
            self.__scheduled_battery_heating_start = start_time
            changed = True
        if self.__scheduled_battery_heating_enabled != enabled:
            self.__scheduled_battery_heating_enabled = enabled
            changed = True

        has_start_time = self.__scheduled_battery_heating_start is not None
        computed_mode = 'on' if has_start_time and self.__scheduled_battery_heating_enabled else 'off'
        computed_start_time = self.__scheduled_battery_heating_start.strftime('%H:%M') if has_start_time else '00:00'
        self.publisher.publish_json(self.get_topic(mqtt_topics.DRIVETRAIN_BATTERY_HEATING_SCHEDULE), {
            'mode': computed_mode,
            'startTime': computed_start_time
        })
        return changed

    def get_topic(self, sub_topic: str):
        return f'{self.mqtt_vin_prefix}/{sub_topic}'

    @staticmethod
    def to_remote_climate(rmt_htd_rr_wnd_st: int) -> str:
        match rmt_htd_rr_wnd_st:
            case 0:
                return 'off'
            case 1:
                return 'blowingonly'
            case 2:
                return 'on'
            case 5:
                return 'front'

        return f'unknown ({rmt_htd_rr_wnd_st})'

    @staticmethod
    def datetime_to_str(dt: datetime.datetime) -> str:
        return datetime.datetime.astimezone(dt, tz=datetime.timezone.utc).isoformat()

    def set_refresh_mode(self, mode: RefreshMode):
        if (
                mode is not None and
                (
                        self.refresh_mode is None
                        or self.refresh_mode != mode
                )
        ):
            new_mode_value = mode.value
            LOG.info(f"Setting refresh mode to {new_mode_value}")
            self.publisher.publish_str(self.get_topic(mqtt_topics.REFRESH_MODE), new_mode_value)
            # Make sure we never store FORCE as previous refresh mode
            if self.refresh_mode != RefreshMode.FORCE:
                self.previous_refresh_mode = self.refresh_mode
            self.refresh_mode = mode
            LOG.debug(f'Refresh mode set to {new_mode_value}')

    @property
    def has_sunroof(self):
        return self.__get_property_value('Sunroof') != '0'

    @property
    def has_on_off_heated_seats(self):
        return self.__get_property_value('HeatedSeat') == '2'

    @property
    def has_level_heated_seats(self):
        return self.__get_property_value('HeatedSeat') == '1'

    @property
    def has_heated_seats(self):
        return self.has_level_heated_seats or self.has_on_off_heated_seats

    @property
    def is_heated_seats_running(self):
        return (self.__remote_heated_seats_front_right_level + self.__remote_heated_seats_front_left_level) > 0

    @property
    def remote_heated_seats_front_left_level(self):
        return self.__remote_heated_seats_front_left_level

    def update_heated_seats_front_left_level(self, level):
        if not self.__check_heated_seats_level(level):
            return False
        changed = self.__remote_heated_seats_front_left_level != level
        self.__remote_heated_seats_front_left_level = level
        return changed

    @property
    def remote_heated_seats_front_right_level(self):
        return self.__remote_heated_seats_front_right_level

    def update_heated_seats_front_right_level(self, level):
        if not self.__check_heated_seats_level(level):
            return False
        changed = self.__remote_heated_seats_front_right_level != level
        self.__remote_heated_seats_front_right_level = level
        return changed

    def __check_heated_seats_level(self, level: int) -> bool:
        if not self.has_heated_seats:
            return False
        if self.has_level_heated_seats and not (0 <= level <= 3):
            raise ValueError(f'Invalid heated seat level {level}. Range must be from 0 to 3 inclusive')
        if self.has_on_off_heated_seats and not (0 <= level <= 1):
            raise ValueError(f'Invalid heated seat level {level}. Range must be from 0 to 1 inclusive')
        return True

    @property
    def supports_target_soc(self):
        return self.__get_property_value('Battery') == '1'

    def get_actual_battery_capacity(self) -> float | None:
        if self.__total_battery_capacity is not None and self.__total_battery_capacity > 0:
            return float(self.__total_battery_capacity)
        # MG4 "Lux/Trophy"
        elif self.series.startswith('EH32 S'):
            if self.model.startswith('EH32 X3'):
                # MG4 Trophy Extended Range
                return 77.0
            else:
                # MG4 Lux/Trophy 2022
                return 64.0
        # MG4 Standard 2022
        elif self.series.startswith('EH32 L'):
            return 51.0
        # Model: MG5 Electric, variant MG5 SR Comfort
        elif self.series.startswith('EP2CP3'):
            return 50.3
        # Model: MG5 Electric, variant MG5 MR Luxury
        elif self.series.startswith('EP2DP3'):
            return 61.1
        # ZS EV Standard 2021
        elif self.series.startswith('ZS EV S'):
            return 49.0
        else:
            return None

    def __get_property_value(self, property_name: str) -> str | None:
        if property_name in self.properties:
            pdict = self.properties[property_name]
            if pdict is not None and isinstance(pdict, dict) and 'value' in pdict:
                return pdict['value']
        return None

    def get_remote_ac_temperature(self) -> int:
        return self.__remote_ac_temp or DEFAULT_AC_TEMP

    def set_ac_temperature(self, temp) -> bool:
        if temp is None:
            LOG.error("Cannot set AC temperature to None")
            return False
        temp = max(self.get_min_ac_temperature(), min(self.get_max_ac_temperature(), temp))
        if self.__remote_ac_temp != temp:
            self.__remote_ac_temp = temp
            LOG.info(f"Updating remote AC temperature to {temp}")
            self.publisher.publish_int(self.get_topic(mqtt_topics.CLIMATE_REMOTE_TEMPERATURE), temp)
            return True
        return False

    def get_ac_temperature_idx(self) -> int:
        if self.series.startswith('EH32'):
            return 3 + self.get_remote_ac_temperature() - self.get_min_ac_temperature()
        else:
            return 2 + self.get_remote_ac_temperature() - self.get_min_ac_temperature()

    def get_min_ac_temperature(self) -> int:
        if self.series.startswith('EH32'):
            return 17
        else:
            return 16

    def get_max_ac_temperature(self) -> int:
        if self.series.startswith('EH32'):
            return 33
        else:
            return 28

    @property
    def is_remote_ac_running(self) -> bool:
        return self.__remote_ac_running


def has_scheduled_charging_info(charge_mgmt_data: ChrgMgmtData):
    return charge_mgmt_data.bmsReserStHourDspCmd is not None \
        and charge_mgmt_data.bmsReserStMintueDspCmd is not None \
        and charge_mgmt_data.bmsReserSpHourDspCmd is not None \
        and charge_mgmt_data.bmsReserSpMintueDspCmd is not None
