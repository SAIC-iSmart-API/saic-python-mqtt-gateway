import datetime
import logging
import os
from enum import Enum
from typing import cast

import paho.mqtt.client as mqtt
from saic_ismart_client.common_model import ScheduledChargingMode
from saic_ismart_client.ota_v1_1.data_model import VinInfo
from saic_ismart_client.ota_v2_1.data_model import OtaRvmVehicleStatusResp25857
from saic_ismart_client.ota_v3_0.data_model import OtaChrgMangDataResp, RvsChargingStatus
from saic_ismart_client.saic_api import SaicMessage, TargetBatteryCode

import mqtt_topics
from Exceptions import MqttGatewayException
from publisher import Publisher

PRESSURE_TO_BAR_FACTOR = 0.04

logging.basicConfig(format='%(asctime)s %(message)s')
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
    def __init__(self, publisher: Publisher, account_prefix: str, vin: VinInfo, wallbox_soc_topic: str = ''):
        self.publisher = publisher
        self.vin = vin.vin
        self.series = str(vin.series).strip().upper()
        self.mqtt_vin_prefix = f'{account_prefix}'
        self.wallbox_soc_topic = wallbox_soc_topic
        self.last_car_activity = datetime.datetime.min
        self.last_successful_refresh = datetime.datetime.min
        self.last_car_shutdown = datetime.datetime.now()
        self.last_car_vehicle_message = datetime.datetime.min
        # treat high voltage battery as active, if we don't have any other information
        self.hv_battery_active = True
        self.refresh_period_active = -1
        self.refresh_period_inactive = -1
        self.refresh_period_after_shutdown = -1
        self.refresh_period_inactive_grace = -1
        self.target_soc = None
        self.refresh_mode = RefreshMode.OFF
        self.previous_refresh_mode = RefreshMode.OFF
        self.properties = {}
        self.__remote_ac_temp = None
        self.__remote_ac_running = False

    def set_refresh_period_active(self, seconds: int):
        self.publisher.publish_int(self.get_topic(mqtt_topics.REFRESH_PERIOD_ACTIVE), seconds)
        LOG.info(f'Setting active query interval in vehicle handler for VIN {self.vin} to {seconds} seconds')
        self.refresh_period_active = seconds

    def set_refresh_period_inactive(self, seconds: int):
        self.publisher.publish_int(self.get_topic(mqtt_topics.REFRESH_PERIOD_INACTIVE), seconds)
        LOG.info(f'Setting inactive query interval in vehicle handler for VIN {self.vin} to {seconds} seconds')
        self.refresh_period_inactive = seconds

    def set_refresh_period_after_shutdown(self, seconds: int):
        self.publisher.publish_int(self.get_topic(mqtt_topics.REFRESH_PERIOD_AFTER_SHUTDOWN), seconds)
        LOG.info(
            f'Setting after shutdown query interval in vehicle handler for VIN {self.vin} to {seconds} seconds')
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
        if self.target_soc != target_soc:
            self.publisher.publish_int(self.get_topic(mqtt_topics.DRIVETRAIN_SOC_TARGET), target_soc.get_percentage())
            self.target_soc = target_soc

    def is_complete(self) -> bool:
        return self.refresh_period_active != -1 \
            and self.refresh_period_inactive != -1 \
            and self.refresh_period_after_shutdown != -1 \
            and self.refresh_period_inactive_grace != -1 \
            and self.target_soc != -1 \
            and self.refresh_mode

    def handle_vehicle_status(self, vehicle_status: OtaRvmVehicleStatusResp25857) -> None:
        is_engine_running = vehicle_status.is_engine_running()
        is_charging = vehicle_status.is_charging()
        basic_vehicle_status = vehicle_status.get_basic_vehicle_status()
        remote_climate_status = basic_vehicle_status.remote_climate_status

        self.set_hv_battery_active(is_charging or is_engine_running or remote_climate_status > 0)

        self.publisher.publish_bool(self.get_topic(mqtt_topics.DRIVETRAIN_RUNNING), is_engine_running)
        self.publisher.publish_bool(self.get_topic(mqtt_topics.DRIVETRAIN_CHARGING), is_charging)
        interior_temperature = basic_vehicle_status.interior_temperature
        if interior_temperature > -128:
            self.publisher.publish_int(self.get_topic(mqtt_topics.CLIMATE_INTERIOR_TEMPERATURE), interior_temperature)
        exterior_temperature = basic_vehicle_status.exterior_temperature
        if exterior_temperature > -128:
            self.publisher.publish_int(self.get_topic(mqtt_topics.CLIMATE_EXTERIOR_TEMPERATURE), exterior_temperature)
        battery_voltage = basic_vehicle_status.battery_voltage / 10.0
        self.publisher.publish_float(self.get_topic(mqtt_topics.DRIVETRAIN_AUXILIARY_BATTERY_VOLTAGE), battery_voltage)

        way_point = vehicle_status.get_gps_position().get_way_point()
        speed = way_point.speed / 10.0
        self.publisher.publish_float(self.get_topic(mqtt_topics.LOCATION_SPEED), speed)
        self.publisher.publish_int(self.get_topic(mqtt_topics.LOCATION_HEADING), way_point.heading)
        position = way_point.get_position()
        latitude = None
        if abs(position.latitude) > 0:
            latitude = position.latitude / 1000000.0
            self.publisher.publish_float(self.get_topic(mqtt_topics.LOCATION_LATITUDE), latitude)
        longitude = None
        if abs(position.longitude) > 0:
            longitude = position.longitude / 1000000.0
            self.publisher.publish_float(self.get_topic(mqtt_topics.LOCATION_LONGITUDE), longitude)
        self.publisher.publish_int(self.get_topic(mqtt_topics.LOCATION_ELEVATION), position.altitude)
        if latitude is not None and longitude is not None:
            self.publisher.publish_json(self.get_topic(mqtt_topics.LOCATION_POSITION), {
                'latitude': latitude,
                'longitude': longitude,
            })

        self.publisher.publish_bool(self.get_topic(mqtt_topics.WINDOWS_DRIVER), basic_vehicle_status.driver_window)
        self.publisher.publish_bool(self.get_topic(mqtt_topics.WINDOWS_PASSENGER),
                                    basic_vehicle_status.passenger_window)
        self.publisher.publish_bool(self.get_topic(mqtt_topics.WINDOWS_REAR_LEFT),
                                    basic_vehicle_status.rear_left_window)
        self.publisher.publish_bool(self.get_topic(mqtt_topics.WINDOWS_REAR_RIGHT),
                                    basic_vehicle_status.rear_right_window)
        self.publisher.publish_bool(self.get_topic(mqtt_topics.WINDOWS_SUN_ROOF), basic_vehicle_status.sun_roof_status)

        self.publisher.publish_bool(self.get_topic(mqtt_topics.DOORS_LOCKED), basic_vehicle_status.lock_status)
        self.publisher.publish_bool(self.get_topic(mqtt_topics.DOORS_DRIVER), basic_vehicle_status.driver_door)
        self.publisher.publish_bool(self.get_topic(mqtt_topics.DOORS_PASSENGER), basic_vehicle_status.passenger_door)
        self.publisher.publish_bool(self.get_topic(mqtt_topics.DOORS_REAR_LEFT), basic_vehicle_status.rear_left_door)
        self.publisher.publish_bool(self.get_topic(mqtt_topics.DOORS_REAR_RIGHT), basic_vehicle_status.rear_right_door)
        self.publisher.publish_bool(self.get_topic(mqtt_topics.DOORS_BONNET), basic_vehicle_status.bonnet_status)
        self.publisher.publish_bool(self.get_topic(mqtt_topics.DOORS_BOOT), basic_vehicle_status.boot_status)

        if (
                basic_vehicle_status.front_left_tyre_pressure is not None
                and basic_vehicle_status.front_left_tyre_pressure > 0
        ):
            front_left_tyre_bar = basic_vehicle_status.front_left_tyre_pressure * PRESSURE_TO_BAR_FACTOR
            self.publisher.publish_float(self.get_topic(mqtt_topics.TYRES_FRONT_LEFT_PRESSURE),
                                         round(front_left_tyre_bar, 2))

        if (
                basic_vehicle_status.front_right_tyre_pressure is not None
                and basic_vehicle_status.front_right_tyre_pressure > 0
        ):
            front_right_tyre_bar = basic_vehicle_status.front_right_tyre_pressure * PRESSURE_TO_BAR_FACTOR
            self.publisher.publish_float(self.get_topic(mqtt_topics.TYRES_FRONT_RIGHT_PRESSURE),
                                         round(front_right_tyre_bar, 2))
        if (
                basic_vehicle_status.rear_left_tyre_pressure
                and basic_vehicle_status.rear_left_tyre_pressure > 0
        ):
            rear_left_tyre_bar = basic_vehicle_status.rear_left_tyre_pressure * PRESSURE_TO_BAR_FACTOR
            self.publisher.publish_float(self.get_topic(mqtt_topics.TYRES_REAR_LEFT_PRESSURE),
                                         round(rear_left_tyre_bar, 2))
        if (
                basic_vehicle_status.rear_right_tyre_pressure is not None
                and basic_vehicle_status.rear_right_tyre_pressure > 0
        ):
            rear_right_tyre_bar = basic_vehicle_status.rear_right_tyre_pressure * PRESSURE_TO_BAR_FACTOR
            self.publisher.publish_float(self.get_topic(mqtt_topics.TYRES_REAR_RIGHT_PRESSURE),
                                         round(rear_right_tyre_bar, 2))

        self.publisher.publish_bool(self.get_topic(mqtt_topics.LIGHTS_MAIN_BEAM), basic_vehicle_status.main_beam_status)
        self.publisher.publish_bool(self.get_topic(mqtt_topics.LIGHTS_DIPPED_BEAM),
                                    basic_vehicle_status.dipped_beam_status)

        self.publisher.publish_str(self.get_topic(mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE),
                                   VehicleState.to_remote_climate(remote_climate_status))
        self.__remote_ac_running = remote_climate_status == 2

        rear_window_heat_state = basic_vehicle_status.rmt_htd_rr_wnd_st
        self.publisher.publish_str(self.get_topic(mqtt_topics.CLIMATE_BACK_WINDOW_HEAT),
                                   'off' if rear_window_heat_state == 0 else 'on')

        if basic_vehicle_status.mileage > 0:
            mileage = basic_vehicle_status.mileage / 10.0
            self.publisher.publish_float(self.get_topic(mqtt_topics.DRIVETRAIN_MILEAGE), mileage)
        if basic_vehicle_status.fuel_range_elec > 0:
            electric_range = basic_vehicle_status.fuel_range_elec / 10.0
            self.publisher.publish_float(self.get_topic(mqtt_topics.DRIVETRAIN_RANGE), electric_range)

        self.publisher.publish_str(self.get_topic(mqtt_topics.REFRESH_LAST_VEHICLE_STATE),
                                   VehicleState.datetime_to_str(datetime.datetime.now()))

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

    def notify_message(self, message: SaicMessage):
        if (
                self.last_car_vehicle_message == datetime.datetime.min
                or message.message_time > self.last_car_vehicle_message
        ):
            self.last_car_vehicle_message = message.message_time
            self.publisher.publish_int(self.get_topic(mqtt_topics.INFO_LAST_MESSAGE_ID), message.message_id)
            self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_LAST_MESSAGE_TYPE), message.message_type)
            self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_LAST_MESSAGE_TITLE), message.title)
            self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_LAST_MESSAGE_TIME),
                                       VehicleState.datetime_to_str(self.last_car_vehicle_message))
            self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_LAST_MESSAGE_SENDER), message.sender)
            if message.content:
                self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_LAST_MESSAGE_CONTENT), message.content)
            self.publisher.publish_int(self.get_topic(mqtt_topics.INFO_LAST_MESSAGE_STATUS), message.read_status)
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
                last_shutdown_plus_refresh = self.last_car_shutdown \
                                             + datetime.timedelta(seconds=float(self.refresh_period_inactive_grace))
                if self.last_successful_refresh is None:
                    self.mark_successful_refresh()
                    return True

                if self.last_car_activity > self.last_successful_refresh:
                    return True

                if self.hv_battery_active:
                    result = self.last_successful_refresh < datetime.datetime.now() - datetime.timedelta(
                        seconds=float(self.refresh_period_active))
                    LOG.debug(f'HV battery is active. Should refresh: {result}')
                    return result

                if last_shutdown_plus_refresh > datetime.datetime.now():
                    result = self.last_successful_refresh < datetime.datetime.now() - datetime.timedelta(
                        seconds=float(self.refresh_period_after_shutdown))
                    LOG.debug(f'Refresh grace period after shutdown has not passed. Should refresh: {result}')
                    return result

                result = self.last_successful_refresh < datetime.datetime.now() - datetime.timedelta(
                    seconds=float(self.refresh_period_inactive))
                LOG.debug(
                    f'HV battery is inactive and refresh period after shutdown is over. Should refresh: {result}'
                )
                return result

    def mark_successful_refresh(self):
        self.last_successful_refresh = datetime.datetime.now()

    def configure(self, vin_info: VinInfo):
        self.publisher.publish_str(self.get_topic(mqtt_topics.INTERNAL_CONFIGURATION_RAW),
                                   vin_info.model_configuration_json_str)
        self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_BRAND), vin_info.brand_name.decode())
        self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_MODEL), vin_info.model_name.decode())
        self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_YEAR), vin_info.model_year)
        self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_SERIES), vin_info.series)
        if vin_info.color_name:
            self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_COLOR), vin_info.color_name.decode())
        self.properties = {}
        for c in vin_info.model_configuration_json_str.split(';'):
            property_map = {}
            if ',' in c:
                for e in c.split(','):
                    if ':' in e:
                        key_value_pair = e.split(":")
                        property_map[key_value_pair[0]] = key_value_pair[1]
                property_name = property_map["name"]
                property_code = property_map["code"]
                property_value = property_map["value"]
                property_code_topic = f'{mqtt_topics.INFO_CONFIGURATION}/{property_code}'
                property_name_topic = f'{mqtt_topics.INFO_CONFIGURATION}/{property_name}'
                self.properties[property_name] = {'code': property_code, 'value': property_value}
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
        # Make sure the only refresh mode that is not supported at start is RefreshMode.PERIODIC
        if self.refresh_mode in [RefreshMode.OFF, RefreshMode.FORCE]:
            self.set_refresh_mode(RefreshMode.PERIODIC)
        if self.__remote_ac_temp is None:
            self.set_ac_temperature(22)

    def configure_by_message(self, topic: str, msg: mqtt.MQTTMessage):
        payload = msg.payload.decode().lower()
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

    def handle_charge_status(self, charge_mgmt_data: OtaChrgMangDataResp) -> None:
        self.publisher.publish_float(self.get_topic(mqtt_topics.DRIVETRAIN_CURRENT),
                                     round(charge_mgmt_data.get_current(), 3))
        self.publisher.publish_float(self.get_topic(mqtt_topics.DRIVETRAIN_VOLTAGE),
                                     round(charge_mgmt_data.get_voltage(), 3))
        self.publisher.publish_float(self.get_topic(mqtt_topics.DRIVETRAIN_POWER),
                                     round(charge_mgmt_data.get_power(), 3))
        target_soc = charge_mgmt_data.get_charge_target_soc()
        if target_soc is not None:
            self.update_target_soc(target_soc)

        soc = charge_mgmt_data.bmsPackSOCDsp / 10.0
        if soc <= 100.0:
            self.publisher.publish_float(self.get_topic(mqtt_topics.DRIVETRAIN_SOC), soc)
            if self.wallbox_soc_topic:
                self.publisher.publish_int(self.wallbox_soc_topic, int(soc), True)
        estimated_electrical_range = charge_mgmt_data.bms_estd_elec_rng / 10.0
        self.publisher.publish_float(self.get_topic(mqtt_topics.DRIVETRAIN_HYBRID_ELECTRICAL_RANGE),
                                     estimated_electrical_range)
        charge_status = cast(RvsChargingStatus, charge_mgmt_data.chargeStatus)
        if (
                charge_status.mileage_of_day is not None
                and charge_status.mileage_of_day > 0
        ):
            mileage_of_the_day = charge_status.mileage_of_day / 10.0
            self.publisher.publish_float(self.get_topic(mqtt_topics.DRIVETRAIN_MILEAGE_OF_DAY), mileage_of_the_day)
        if (
                charge_status.mileage_since_last_charge is not None
                and charge_status.mileage_since_last_charge > 0
        ):
            mileage_since_last_charge = charge_status.mileage_since_last_charge / 10.0
            self.publisher.publish_float(self.get_topic(mqtt_topics.DRIVETRAIN_MILEAGE_SINCE_LAST_CHARGE),
                                         mileage_since_last_charge)
        soc_kwh = charge_status.real_time_power / 10.0
        self.publisher.publish_float(self.get_topic(mqtt_topics.DRIVETRAIN_SOC_KWH), soc_kwh)
        self.publisher.publish_int(self.get_topic(mqtt_topics.DRIVETRAIN_CHARGING_TYPE), charge_status.charging_type)
        self.publisher.publish_bool(self.get_topic(mqtt_topics.DRIVETRAIN_CHARGER_CONNECTED),
                                    charge_status.charging_gun_state)

        if has_scheduled_charging_info(charge_mgmt_data):
            try:
                self.publisher.publish_json(self.get_topic(mqtt_topics.DRIVETRAIN_CHARGING_SCHEDULE), {
                    'startTime': "{:02d}:{:02d}".format(charge_mgmt_data.bmsReserStHourDspCmd,
                                                        charge_mgmt_data.bmsReserStMintueDspCmd),
                    'endTime': "{:02d}:{:02d}".format(charge_mgmt_data.bmsReserSpHourDspCmd,
                                                      charge_mgmt_data.bmsReserSpMintueDspCmd),
                    'mode': ScheduledChargingMode(charge_mgmt_data.bmsReserCtrlDspCmd).name,
                })
            except ValueError:
                LOG.exception("Error parsing scheduled charging info")

        # Only publish remaining charging time if the car is charging and we have current flowing
        if charge_status.charging_gun_state and charge_mgmt_data.get_current() < 0:
            self.publisher.publish_int(self.get_topic(mqtt_topics.DRIVETRAIN_REMAINING_CHARGING_TIME),
                                       charge_mgmt_data.chrgngRmnngTime * 60)
        else:
            self.publisher.publish_int(self.get_topic(mqtt_topics.DRIVETRAIN_REMAINING_CHARGING_TIME), 0)
        self.publisher.publish_str(self.get_topic(mqtt_topics.REFRESH_LAST_CHARGE_STATE),
                                   VehicleState.datetime_to_str(datetime.datetime.now()))
        if (
                charge_status.last_charge_ending_power is not None
                and charge_status.last_charge_ending_power > 0
        ):
            last_charge_ending_power = charge_status.last_charge_ending_power / 10.0
            self.publisher.publish_float(self.get_topic(mqtt_topics.DRIVETRAIN_LAST_CHARGE_ENDING_POWER),
                                         last_charge_ending_power)
        if (
                charge_status.total_battery_capacity is not None
                and charge_status.total_battery_capacity > 0
        ):
            total_battery_capacity = charge_status.total_battery_capacity / 10.0
            self.publisher.publish_float(self.get_topic(mqtt_topics.DRIVETRAIN_TOTAL_BATTERY_CAPACITY),
                                         total_battery_capacity)

    def get_topic(self, sub_topic: str):
        return f'{self.mqtt_vin_prefix}/{sub_topic}'

    @staticmethod
    def to_remote_climate(rmt_htd_rr_wnd_st: int) -> str:
        match rmt_htd_rr_wnd_st:
            case 0:
                return 'off'
            case 1:
                return 'blowingOnly'
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

    def has_sunroof(self):
        return self.__get_property_value('Sunroof') != '0'

    def has_heated_seats(self):
        return self.__get_property_value('HeatedSeat') == '0'

    def __get_property_value(self, property_name: str) -> str | None:
        if property_name in self.properties:
            pdict = self.properties[property_name]
            if pdict is not None and isinstance(pdict, dict) and 'value' in pdict:
                return pdict['value']
        return None

    def set_ac_temperature(self, temp) -> bool:
        temp = max(self.get_min_ac_temperature(), min(self.get_max_ac_temperature(), temp))
        if (self.__remote_ac_temp is None) or (self.__remote_ac_temp != temp):
            self.__remote_ac_temp = temp
            self.publisher.publish_int(self.get_topic(mqtt_topics.CLIMATE_REMOTE_TEMPERATURE), temp)
            return True
        return False

    def get_ac_temperature_idx(self):
        if self.series.startswith('EH32'):
            return 3 + self.__remote_ac_temp - self.get_min_ac_temperature()
        else:
            return 2 + self.__remote_ac_temp - self.get_min_ac_temperature()

    def get_min_ac_temperature(self):
        if self.series.startswith('EH32'):
            return 17
        else:
            return 16

    def get_max_ac_temperature(self):
        if self.series.startswith('EH32'):
            return 33
        else:
            return 28

    def is_remote_ac_running(self):
        return self.__remote_ac_running


def has_scheduled_charging_info(charge_mgmt_data: OtaChrgMangDataResp):
    return charge_mgmt_data.bmsReserStHourDspCmd is not None \
        and charge_mgmt_data.bmsReserStMintueDspCmd is not None \
        and charge_mgmt_data.bmsReserSpHourDspCmd is not None \
        and charge_mgmt_data.bmsReserSpMintueDspCmd is not None
