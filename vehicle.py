import datetime
import logging
import os
from typing import cast

from saic_ismart_client.ota_v1_1.data_model import VinInfo
from saic_ismart_client.ota_v2_1.data_model import OtaRvmVehicleStatusResp25857
from saic_ismart_client.ota_v3_0.data_model import OtaChrgMangDataResp, RvsChargingStatus
from saic_ismart_client.saic_api import SaicMessage

import mqtt_topics
import refresh_mode
from publisher import Publisher

PRESSURE_TO_BAR_FACTOR = 0.04

logging.basicConfig(format='%(asctime)s %(message)s')
logging.getLogger().setLevel(level=os.getenv('LOG_LEVEL', 'INFO').upper())


class VehicleState:
    def __init__(self, publisher: Publisher, account_prefix: str, vin: str, openwb_lp_topic: str = ''):
        self.publisher = publisher
        self.vin = vin
        self.mqtt_vin_prefix = f'{account_prefix}/{mqtt_topics.VEHICLES}/{self.vin}'
        self.openwb_lp_topic = openwb_lp_topic
        self.last_car_activity = datetime.datetime.min
        self.last_successful_refresh = datetime.datetime.min
        self.last_car_shutdown = datetime.datetime.now()
        self.last_car_vehicle_message = datetime.datetime.min
        # treat high voltage battery as active, if we don't have any other information
        self.hv_battery_active = True
        self.refresh_period_active = -1
        self.refresh_period_inactive = -1
        self.refresh_period_after_shutdown = -1
        self.refresh_mode = ''
        self.previous_refresh_mode = ''
        self.is_charging_on_openwb = False

    def set_refresh_period_active(self, seconds: int):
        self.publisher.publish_int(self.get_topic(mqtt_topics.REFRESH_PERIOD_ACTIVE), seconds)
        logging.info(f'Setting active query interval in vehicle handler for VIN {self.vin} to {seconds} seconds')
        self.refresh_period_active = seconds

    def set_refresh_period_inactive(self, seconds: int):
        self.publisher.publish_int(self.get_topic(mqtt_topics.REFRESH_PERIOD_INACTIVE), seconds)
        logging.info(f'Setting inactive query interval in vehicle handler for VIN {self.vin} to {seconds} seconds')
        self.refresh_period_inactive = seconds

    def set_refresh_period_after_shutdown(self, refresh_period_after_shutdown: int):
        if (
                self.refresh_period_after_shutdown == -1
                or self.refresh_period_after_shutdown != refresh_period_after_shutdown
        ):
            self.publisher.publish_int(self.get_topic(mqtt_topics.REFRESH_PERIOD_INACTIVE_GRACE),
                                       refresh_period_after_shutdown)
            self.refresh_period_after_shutdown = refresh_period_after_shutdown

    def is_complete(self) -> bool:
        return self.refresh_period_active != -1 \
            and self.refresh_period_inactive != -1\
            and self.refresh_period_after_shutdown != 1\
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
        if abs(position.latitude) > 0:
            latitude = position.latitude / 1000000.0
            self.publisher.publish_float(self.get_topic(mqtt_topics.LOCATION_LATITUDE), latitude)
        if abs(position.longitude) > 0:
            longitude = position.longitude / 1000000.0
            self.publisher.publish_float(self.get_topic(mqtt_topics.LOCATION_LONGITUDE), longitude)
        self.publisher.publish_int(self.get_topic(mqtt_topics.LOCATION_ELEVATION), position.altitude)

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
        self.publisher.publish_int(self.get_topic(mqtt_topics.CLIMATE_BACK_WINDOW_HEAT),
                                   basic_vehicle_status.rmt_htd_rr_wnd_st)

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
            case refresh_mode.OFF:
                return False
            case refresh_mode.FORCE:
                self.set_refresh_mode(self.previous_refresh_mode)
                return True
            # refresh_mode.PERIODIC is treated like default
            case _:
                last_shutdown_plus_refresh = self.last_car_shutdown\
                                             + datetime.timedelta(seconds=float(self.refresh_period_after_shutdown))
                if self.last_successful_refresh is None:
                    self.mark_successful_refresh()
                    return True
                if self.last_car_activity > self.last_successful_refresh:
                    return True
                if (
                    self.hv_battery_active
                    or last_shutdown_plus_refresh > datetime.datetime.now()
                ):
                    logging.debug('HV battery is active or refresh period after shutdown has passed')
                    return self.last_successful_refresh < datetime.datetime.now()\
                        - datetime.timedelta(seconds=float(self.refresh_period_active))
                else:
                    logging.debug('HV battery is inactive or refresh period after shutdown is not over yet')
                    return self.last_successful_refresh < datetime.datetime.now()\
                        - datetime.timedelta(seconds=float(self.refresh_period_inactive))

    def mark_successful_refresh(self):
        self.last_successful_refresh = datetime.datetime.now()

    def configure(self, vin_info: VinInfo):
        self.publisher.publish_str(self.get_topic(mqtt_topics.INTERNAL_CONFIGURATION_RAW),
                                   vin_info.model_configuration_json_str)
        self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_BRAND), vin_info.brand_name)
        self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_MODEL), vin_info.model_name)
        self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_YEAR), vin_info.model_year)
        self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_SERIES), vin_info.series)
        if vin_info.color_name:
            self.publisher.publish_str(self.get_topic(mqtt_topics.INFO_COLOR), vin_info.color_name)
        for c in vin_info.model_configuration_json_str.split(';'):
            property_map = {}
            if ',' in c:
                for e in c.split(','):
                    if ':' in e:
                        key_value_pair = e.split(":")
                        property_map[key_value_pair[0]] = key_value_pair[1]
                self.publisher.publish_str(self.get_topic(f'{mqtt_topics.INFO_CONFIGURATION}/{property_map["code"]}'),
                                           property_map["value"])

    def configure_missing(self):
        if self.refresh_period_active == -1:
            self.set_refresh_period_active(30)
        if self.refresh_period_inactive == -1:
            # in seconds (Once a day to protect your 12V battery)
            self.set_refresh_period_inactive(86400)
        if self.refresh_period_after_shutdown == -1:
            self.set_refresh_period_after_shutdown(600)
        if not self.refresh_mode:
            self.set_refresh_mode(refresh_mode.PERIODIC)

    def configure(self, topic: str, message):
        match topic:
            case mqtt_topics.REFRESH_MODE:
                logging.debug('Setting refresh mode')
                # TODO check for known value and set refresh mode
            case mqtt_topics.REFRESH_PERIOD_ACTIVE:
                logging.debug('')
            case mqtt_topics.REFRESH_PERIOD_INACTIVE:
                logging.debug('')
            case mqtt_topics.REFRESH_PERIOD_INACTIVE_GRACE:
                logging.debug('')
            case _:
                logging.debug('')

    def handle_charge_status(self, charge_mgmt_data: OtaChrgMangDataResp) -> None:
        self.publisher.publish_float(self.get_topic(mqtt_topics.DRIVETRAIN_CURRENT),
                                     round(charge_mgmt_data.get_current(), 3))
        self.publisher.publish_float(self.get_topic(mqtt_topics.DRIVETRAIN_VOLTAGE),
                                     round(charge_mgmt_data.get_voltage(), 3))
        self.publisher.publish_float(self.get_topic(mqtt_topics.DRIVETRAIN_POWER),
                                     round(charge_mgmt_data.get_power(), 3))

        soc = charge_mgmt_data.bmsPackSOCDsp / 10.0
        if soc <= 100.0:
            self.publisher.publish_float(self.get_topic(mqtt_topics.DRIVETRAIN_SOC), soc)
            if self.openwb_lp_topic:
                self.publisher.publish_int(self.openwb_lp_topic, int(soc), True)
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
            case 2:
                return 'on'
            case 5:
                return 'front'

        return f'unknown ({rmt_htd_rr_wnd_st})'

    @staticmethod
    def datetime_to_str(dt: datetime.datetime) -> str:
        return dt.strftime('%Y-%m-%d %H:%M:%S')

    def set_refresh_mode(self, mode: str):
        if (
                self.refresh_mode is None
                or self.refresh_mode != mode
        ):
            self.publisher.publish_str(self.get_topic(mqtt_topics.REFRESH_MODE), mode)
            self.previous_refresh_mode = self.refresh_mode
            self.refresh_mode = mode
