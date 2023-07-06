import argparse
import asyncio
import datetime
import logging
import os
import time
import urllib.parse
from typing import cast

import saic_ismart_client.saic_api
from saic_ismart_client.abrp_api import AbrpApi, AbrpApiException
from saic_ismart_client.ota_v1_1.data_model import VinInfo, MpUserLoggingInRsp, MpAlarmSettingType
from saic_ismart_client.ota_v2_1.data_model import OtaRvmVehicleStatusResp25857
from saic_ismart_client.ota_v3_0.data_model import OtaChrgMangDataResp, RvsChargingStatus
from saic_ismart_client.saic_api import SaicApi, SaicApiException, SaicMessage

from configuration import Configuration
from mqtt_publisher import MqttClient
from publisher import Publisher

MSG_CMD_SUCCESSFUL = 'Success'
PRESSURE_TO_BAR_FACTOR = 0.04


def epoch_value_to_str(time_value: int) -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time_value))


def datetime_to_str(dt: datetime.datetime) -> str:
    return dt.strftime('%Y-%m-%d %H:%M:%S')


logging.basicConfig(format='%(asctime)s %(message)s')
logging.getLogger().setLevel(level=os.getenv('LOG_LEVEL', 'INFO').upper())


class VehicleHandler:
    def __init__(self, config: Configuration, saicapi: SaicApi, publisher: Publisher, vin_info: VinInfo,
                 open_wb_lp: str = None):
        self.configuration = config
        self.saic_api = saicapi
        self.publisher = publisher
        self.vin_info = vin_info
        self.open_wb_lp = open_wb_lp
        self.last_car_activity = None
        self.force_update = True
        self.is_charging_on_openwb = False
        if vin_info.vin in self.configuration.abrp_token_map:
            abrp_user_token = self.configuration.abrp_token_map[vin_info.vin]
        else:
            abrp_user_token = None
        self.abrp_api = AbrpApi(self.configuration.abrp_api_key, abrp_user_token)
        self.vehicle_prefix = f'{self.configuration.saic_user}/vehicles/{self.vin_info.vin}'
        self.refresh_mode = 'periodic'
        self.inactive_refresh_interval = -1
        self.active_refresh_interval = -1

    def set_inactive_refresh_interval(self, seconds: int):
        refresh_prefix = f'{self.vehicle_prefix}/refresh'
        self.publisher.publish_int(f'{refresh_prefix}/period/inActive', seconds)
        self.inactive_refresh_interval = seconds

    def set_active_refresh_interval(self, seconds: int):
        refresh_prefix = f'{self.vehicle_prefix}/refresh'
        self.publisher.publish_int(f'{refresh_prefix}/period/active', seconds)
        self.active_refresh_interval = seconds

    def update_doors_lock_state(self, doors_locked: bool):
        result_key = f'{self.vehicle_prefix}/doors/locked/result'
        try:
            if doors_locked:
                logging.info(f'Vehicle {self.vin_info.vin} will be locked')
                self.saic_api.lock_vehicle(self.vin_info)
            else:
                logging.info(f'Vehicle {self.vin_info.vin} will be unlocked')
                self.saic_api.unlock_vehicle(self.vin_info)
            self.publisher.publish_str(result_key, MSG_CMD_SUCCESSFUL)
            self.force_update = True
        except SaicApiException as e:
            self.publisher.publish_str(result_key, f'Failed: {e.message}')
            logging.exception('update_doors_lock_state failed', exc_info=e)

    def update_rear_window_heat_state(self, rear_window_heat_state: str):
        result_key = f'{self.vehicle_prefix}/climate/rearWindowDefrosterHeating/result'
        try:
            if rear_window_heat_state.lower() == 'on':
                logging.info('Rear window heating will be switched on')
                self.saic_api.start_rear_window_heat(self.vin_info)
                self.publisher.publish_str(result_key, MSG_CMD_SUCCESSFUL)
            elif rear_window_heat_state.lower() == 'off':
                logging.info('Rear window heating will be switched off')
                self.saic_api.stop_rear_window_heat(self.vin_info)
                self.publisher.publish_str(result_key, MSG_CMD_SUCCESSFUL)
            else:
                message = f'Invalid rear window heat state: {rear_window_heat_state}. Valid values are on and off'
                self.publisher.publish_str(result_key, message)
                logging.error(message)
        except SaicApiException as e:
            self.publisher.publish_str(result_key, f'Failed: {e.message}')
            logging.exception('update_rear_window_heat_state failed', exc_info=e)

    def update_front_window_heat_state(self, front_window_heat_state: str):
        result_key = f'{self.vehicle_prefix}/climate/frontWindowDefrosterHeating/result'
        try:
            if front_window_heat_state.lower() == 'on':
                logging.info('Front window heating will be switched on')
                self.saic_api.start_front_defrost(self.vin_info)
                self.publisher.publish_str(result_key, MSG_CMD_SUCCESSFUL)
            elif front_window_heat_state.lower() == 'off':
                logging.info('Front window heating will be switched off')
                self.saic_api.stop_front_defrost(self.vin_info)
                self.publisher.publish_str(result_key, MSG_CMD_SUCCESSFUL)
            else:
                message = f'Invalid front window heat state: {front_window_heat_state}. Valid values are on and off'
                self.publisher.publish_str(result_key, message)
        except SaicApiException as e:
            self.publisher.publish_str(result_key, f'Failed: {e.message}')
            logging.exception('update_front_window_heat_state failed', exc_info=e)

    def update_ac_state(self, ac_state: str):
        result_key = f'{self.vehicle_prefix}/climate/remoteClimateState/result'
        try:
            if ac_state.lower() == 'on':
                logging.info('A/C will be switched on')
                self.saic_api.start_ac(self.vin_info)
                self.publisher.publish_str(result_key, MSG_CMD_SUCCESSFUL)
            elif ac_state.lower() == 'off':
                logging.info('A/C will be switched off')
                self.saic_api.stop_ac(self.vin_info)
                self.publisher.publish_str(result_key, MSG_CMD_SUCCESSFUL)
            else:
                message = f'Invalid A/C state: {ac_state}. Valid values are on and off'
                self.publisher.publish_str(result_key, message)
        except SaicApiException as e:
            self.publisher.publish_str(result_key, f'Failed: {e.message}')
            logging.exception('update_ac_state failed', exc_info=e)

    def refresh_required(self):
        refresh_interval = self.inactive_refresh_interval
        now_minus_refresh_interval = datetime.datetime.now() - datetime.timedelta(seconds=float(refresh_interval))
        if (
                self.refresh_mode != 'off'
                and (
                self.last_car_activity is None
                or self.force_update
                or self.last_car_activity < now_minus_refresh_interval
        )
        ):
            return True
        else:
            return False

    async def handle_vehicle(self) -> None:
        self.set_inactive_refresh_interval(self.configuration.inactive_vehicle_state_refresh_interval)
        self.set_active_refresh_interval(30)
        self.publisher.publish_str(f'{self.vehicle_prefix}/configuration/raw',
                                   self.vin_info.model_configuration_json_str)
        configuration_prefix = f'{self.vehicle_prefix}/configuration'
        for c in self.vin_info.model_configuration_json_str.split(';'):
            property_map = {}
            if ',' in c:
                for e in c.split(','):
                    if ':' in e:
                        key_value_pair = e.split(":")
                        property_map[key_value_pair[0]] = key_value_pair[1]
                self.publisher.publish_str(f'{configuration_prefix}/{property_map["code"]}', property_map["value"])
        while True:
            if self.refresh_required():
                self.force_update = False
                # reset previous refresh mode
                self.publisher.reset_force_mode(self.vin_info.vin, self.refresh_mode)
                try:
                    vehicle_status = self.update_vehicle_status()
                    last_vehicle_status = datetime.datetime.now()
                    charge_status = self.update_charge_status()
                    last_charge_status = datetime.datetime.now()
                    self.abrp_api.update_abrp(vehicle_status, charge_status)
                    self.notify_car_activity(datetime.datetime.now())
                    refresh_prefix = f'{self.vehicle_prefix}/refresh'
                    self.publisher.publish_str(f'{refresh_prefix}/lastVehicleState',
                                               datetime_to_str(last_vehicle_status))
                    self.publisher.publish_str(f'{refresh_prefix}/lastChargeState', datetime_to_str(last_charge_status))
                    if (
                            vehicle_status.is_charging()
                            or self.is_charging_on_openwb
                            or vehicle_status.is_engine_running()
                    ):
                        self.force_update = True
                        await asyncio.sleep(float(self.active_refresh_interval))
                except SaicApiException as e:
                    logging.exception('handle_vehicle loop failed during SaicApi call', exc_info=e)
                    await asyncio.sleep(float(30))
                except AbrpApiException as ae:
                    logging.exception('handle_vehicle loop failed during AbrpApi call', exc_info=ae)
            else:
                # car not active, wait a second
                logging.debug(f'sleeping {datetime.datetime.now()}, last car activity: {self.last_car_activity}')
                await asyncio.sleep(1.0)

    def notify_car_activity(self, last_activity_time: datetime):
        if (
                self.last_car_activity is None
                or self.last_car_activity < last_activity_time
        ):
            self.last_car_activity = last_activity_time
            last_activity = datetime_to_str(self.last_car_activity)
            self.publisher.publish_str(f'{self.vin_info.vin}/last_activity', last_activity)
            logging.info(f'last activity: {last_activity}')

    def force_update_by_message_time(self, message: SaicMessage):
        # something happened, better check the vehicle state
        if (
                self.last_car_activity < message.message_time
        ) or (
                is_vehicle_start_message(message)
                and
                self.configuration.ignore_vehicle_start_message_timestamp
        ):
            self.force_update = True

    def update_vehicle_status(self) -> OtaRvmVehicleStatusResp25857:
        vehicle_status_rsp_msg = self.saic_api.get_vehicle_status_with_retry(self.vin_info)

        vehicle_status_response = cast(OtaRvmVehicleStatusResp25857, vehicle_status_rsp_msg.application_data)
        basic_vehicle_status = vehicle_status_response.get_basic_vehicle_status()
        drivetrain_prefix = f'{self.vehicle_prefix}/drivetrain'
        self.publisher.publish_bool(f'{drivetrain_prefix}/running', vehicle_status_response.is_engine_running())
        self.publisher.publish_bool(f'{drivetrain_prefix}/charging', vehicle_status_response.is_charging())
        battery_voltage = basic_vehicle_status.battery_voltage / 10.0
        self.publisher.publish_float(f'{drivetrain_prefix}/auxiliaryBatteryVoltage', battery_voltage)
        if basic_vehicle_status.mileage > 0:
            mileage = basic_vehicle_status.mileage / 10.0
            self.publisher.publish_float(f'{drivetrain_prefix}/mileage', mileage)
        if basic_vehicle_status.fuel_range_elec > 0:
            electric_range = basic_vehicle_status.fuel_range_elec / 10.0
            self.publisher.publish_float(f'{drivetrain_prefix}/range', electric_range)

        climate_prefix = f'{self.vehicle_prefix}/climate'
        interior_temperature = basic_vehicle_status.interior_temperature
        if interior_temperature > -128:
            self.publisher.publish_int(f'{climate_prefix}/interiorTemperature', interior_temperature)
        exterior_temperature = basic_vehicle_status.exterior_temperature
        if exterior_temperature > -128:
            self.publisher.publish_int(f'{climate_prefix}/exteriorTemperature', exterior_temperature)
        self.publisher.publish_int(f'{climate_prefix}/remoteClimateState',
                                   basic_vehicle_status.remote_climate_status)
        remote_rear_window_defroster_state = basic_vehicle_status.rmt_htd_rr_wnd_st
        self.publisher.publish_int(f'{climate_prefix}/rearWindowDefrosterHeating', remote_rear_window_defroster_state)

        location_prefix = f'{self.vehicle_prefix}/location'
        way_point = vehicle_status_response.get_gps_position().get_way_point()
        speed = way_point.speed / 10.0
        self.publisher.publish_float(f'{location_prefix}/speed', speed)
        self.publisher.publish_int(f'{location_prefix}/heading', way_point.heading)
        position = way_point.get_position()
        if abs(position.latitude) > 0:
            latitude = position.latitude / 1000000.0
            self.publisher.publish_float(f'{location_prefix}/latitude', latitude)
        if abs(position.longitude) > 0:
            longitude = position.longitude / 1000000.0
            self.publisher.publish_float(f'{location_prefix}/longitude', longitude)
        self.publisher.publish_int(f'{location_prefix}/elevation', position.altitude)

        windows_prefix = f'{self.vehicle_prefix}/windows'
        self.publisher.publish_bool(f'{windows_prefix}/driver', basic_vehicle_status.driver_window)
        self.publisher.publish_bool(f'{windows_prefix}/passenger', basic_vehicle_status.passenger_window)
        self.publisher.publish_bool(f'{windows_prefix}/rearLeft', basic_vehicle_status.rear_left_window)
        self.publisher.publish_bool(f'{windows_prefix}/rearRight', basic_vehicle_status.rear_right_window)
        self.publisher.publish_bool(f'{windows_prefix}/sunRoof', basic_vehicle_status.sun_roof_status)

        doors_prefix = f'{self.vehicle_prefix}/doors'
        self.publisher.publish_bool(f'{doors_prefix}/locked', basic_vehicle_status.lock_status)
        self.publisher.publish_bool(f'{doors_prefix}/driver', basic_vehicle_status.driver_door)
        self.publisher.publish_bool(f'{doors_prefix}/passenger', basic_vehicle_status.passenger_door)
        self.publisher.publish_bool(f'{doors_prefix}/rearLeft', basic_vehicle_status.rear_left_door)
        self.publisher.publish_bool(f'{doors_prefix}/rearRight', basic_vehicle_status.rear_right_door)
        self.publisher.publish_bool(f'{doors_prefix}/bonnet', basic_vehicle_status.bonnet_status)
        self.publisher.publish_bool(f'{doors_prefix}/boot', basic_vehicle_status.boot_status)

        tyres_prefix = f'{self.vehicle_prefix}/tyres'
        if (
                basic_vehicle_status.front_left_tyre_pressure is not None
                and basic_vehicle_status.front_left_tyre_pressure > 0
        ):
            # convert value from psi to bar
            front_left_tyre_bar = basic_vehicle_status.front_left_tyre_pressure * PRESSURE_TO_BAR_FACTOR
            self.publisher.publish_float(f'{tyres_prefix}/frontLeftPressure', round(front_left_tyre_bar, 2))
        if (
                basic_vehicle_status.front_right_tyre_pressure is not None
                and basic_vehicle_status.front_right_tyre_pressure > 0
        ):
            front_right_tyre_bar = basic_vehicle_status.front_right_tyre_pressure * PRESSURE_TO_BAR_FACTOR
            self.publisher.publish_float(f'{tyres_prefix}/frontRightPressure', round(front_right_tyre_bar, 2))
        if (
                basic_vehicle_status.rear_left_tyre_pressure
                and basic_vehicle_status.rear_left_tyre_pressure > 0
        ):
            rear_left_tyre_bar = basic_vehicle_status.rear_left_tyre_pressure * PRESSURE_TO_BAR_FACTOR
            self.publisher.publish_float(f'{tyres_prefix}/rearLeftPressure', round(rear_left_tyre_bar, 2))
        if (
                basic_vehicle_status.rear_right_tyre_pressure is not None
                and basic_vehicle_status.rear_right_tyre_pressure > 0
        ):
            rear_right_tyre_bar = basic_vehicle_status.rear_right_tyre_pressure * PRESSURE_TO_BAR_FACTOR
            self.publisher.publish_float(f'{tyres_prefix}/rearRightPressure', round(rear_right_tyre_bar, 2))

        lights_prefix = f'{self.vehicle_prefix}/lights'
        self.publisher.publish_bool(f'{lights_prefix}/mainBeam', basic_vehicle_status.main_beam_status)
        self.publisher.publish_bool(f'{lights_prefix}/dippedBeam', basic_vehicle_status.dipped_beam_status)

        return vehicle_status_response

    def update_charge_status(self) -> OtaChrgMangDataResp:
        chrg_mgmt_data_rsp_msg = self.saic_api.get_charging_status_with_retry(self.vin_info)
        charge_mgmt_data = cast(OtaChrgMangDataResp, chrg_mgmt_data_rsp_msg.application_data)

        drivetrain_prefix = f'{self.vehicle_prefix}/drivetrain'
        self.publisher.publish_float(f'{drivetrain_prefix}/current', round(charge_mgmt_data.get_current(), 3))
        self.publisher.publish_float(f'{drivetrain_prefix}/voltage', round(charge_mgmt_data.get_voltage(), 3))
        self.publisher.publish_float(f'{drivetrain_prefix}/power', round(charge_mgmt_data.get_power(), 3))
        soc = charge_mgmt_data.bmsPackSOCDsp / 10.0
        if soc <= 100.0:
            self.publisher.publish_float(f'{drivetrain_prefix}/soc', soc)
            if self.open_wb_lp is not None:
                # publish SoC to openWB topic
                topic = f'{self.configuration.open_wb_topic}/set/lp/{self.open_wb_lp}/%Soc'
                self.publisher.publish_int(topic, int(soc), True)
        estimated_electrical_range = charge_mgmt_data.bms_estd_elec_rng / 10.0
        self.publisher.publish_float(f'{drivetrain_prefix}/hybrid_electrical_range', estimated_electrical_range)
        charge_status = cast(RvsChargingStatus, charge_mgmt_data.chargeStatus)
        if (
                charge_status.mileage_of_day is not None
                and charge_status.mileage_of_day > 0
        ):
            mileage_of_the_day = charge_status.mileage_of_day / 10.0
            self.publisher.publish_float(f'{drivetrain_prefix}/mileageOfTheDay', mileage_of_the_day)
        if (
                charge_status.mileage_since_last_charge is not None
                and charge_status.mileage_since_last_charge > 0
        ):
            mileage_since_last_charge = charge_status.mileage_since_last_charge / 10.0
            self.publisher.publish_float(f'{drivetrain_prefix}/mileageSinceLastCharge', mileage_since_last_charge)
        soc_kwh = charge_status.real_time_power / 10.0
        self.publisher.publish_float(f'{drivetrain_prefix}/soc_kwh', soc_kwh)
        self.publisher.publish_int(f'{drivetrain_prefix}/chargingType', charge_status.charging_type)
        self.publisher.publish_bool(f'{drivetrain_prefix}/chargerConnected', charge_status.charging_gun_state)
        if (
                charge_status.last_charge_ending_power is not None
                and charge_status.last_charge_ending_power > 0
        ):
            last_charge_ending_power = charge_status.last_charge_ending_power / 10.0
            self.publisher.publish_float(f'{drivetrain_prefix}/lastChargeEndingPower', last_charge_ending_power)
        if (
                charge_status.total_battery_capacity is not None
                and charge_status.total_battery_capacity > 0
        ):
            total_battery_capacity = charge_status.total_battery_capacity / 10.0
            self.publisher.publish_float(f'{drivetrain_prefix}/totalBatteryCapacity', total_battery_capacity)

        self.publisher.publish_int(f'{self.vin_info.vin}/bms/bmsChrgCtrlDspCmd', charge_mgmt_data.bmsChrgCtrlDspCmd)
        self.publisher.publish_int(f'{self.vin_info.vin}/bms/bmsChrgOtptCrntReq', charge_mgmt_data.bmsChrgOtptCrntReq)
        self.publisher.publish_int(f'{self.vin_info.vin}/bms/bmsChrgSts', charge_mgmt_data.bmsChrgSts)
        self.publisher.publish_int(f'{self.vin_info.vin}/bms/bmsPackVol', charge_mgmt_data.bmsPackVol)
        self.publisher.publish_int(f'{self.vin_info.vin}/bms/bmsPTCHeatReqDspCmd',
                                   charge_mgmt_data.bmsPTCHeatReqDspCmd)
        return charge_mgmt_data


class MqttGateway:
    def __init__(self, config: Configuration):
        self.configuration = config
        self.vehicle_handler = {}
        self.publisher = MqttClient(self.configuration)
        self.publisher.on_refresh_mode_update = self.__on_refresh_mode_update
        self.publisher.on_inactive_refresh_interval_update = self.__on_inactive_refresh_interval_update
        self.publisher.on_active_refresh_interval_update = self.__on_active_refresh_interval_update
        self.publisher.on_doors_lock_state_update = self.__on_doors_lock_state_update
        self.publisher.on_rear_window_heat_state_update = self.__on_rear_window_heat_state_update
        self.publisher.on_front_window_heat_state_update = self.__on_front_window_heat_state_update
        self.publisher.on_ac_state_update = self.__on_ac_state_update
        self.publisher.on_lp_charging = self.__on_lp_charging
        self.saic_api = SaicApi(config.saic_uri, config.saic_user, config.saic_password, config.saic_relogin_delay)
        self.saic_api.on_publish_json_value = self.__on_publish_json_value
        self.saic_api.on_publish_raw_value = self.__on_publish_raw_value
        self.publisher.connect()

    def run(self):
        try:
            login_response_message = self.saic_api.login()
            user_logging_in_response = cast(MpUserLoggingInRsp, login_response_message.application_data)
        except SaicApiException as e:
            logging.exception('MqttGateway crashed due to SaicApiException', exc_info=e)
            raise SystemExit(e)

        for alarm_setting_type in MpAlarmSettingType:
            try:
                alarm_switches = [saic_ismart_client.saic_api.create_alarm_switch(alarm_setting_type)]
                self.saic_api.set_alarm_switches(alarm_switches)
                logging.info(f'Registering for {alarm_setting_type.value} messages')
            except SaicApiException:
                logging.warning(f'Failed to register for {alarm_setting_type.value} messages')

        for info in user_logging_in_response.vin_list:
            vin_info = cast(VinInfo, info)
            info_prefix = f'{self.configuration.saic_user}/vehicles/{vin_info.vin}/info'
            self.publisher.publish_str(f'{info_prefix}/brand', vin_info.brand_name.decode())
            self.publisher.publish_str(f'{info_prefix}/model', vin_info.model_name.decode())
            self.publisher.publish_str(f'{info_prefix}/year', vin_info.model_year)
            self.publisher.publish_str(f'{info_prefix}/series', vin_info.series)
            if vin_info.color_name is not None:
                self.publisher.publish_str(f'{info_prefix}/color', vin_info.color_name.decode())

            vehicle_handler = VehicleHandler(
                self.configuration,  # Gateway pointer
                self.saic_api,
                self.publisher,
                info,
                self.get_open_wb_lp(info.vin))
            self.vehicle_handler[info.vin] = vehicle_handler

        message_handler = MessageHandler(self, self.saic_api)
        asyncio.run(main(self.vehicle_handler, message_handler, self.configuration.messages_request_interval))

    def notify_message(self, message: SaicMessage):
        message_prefix = f'{self.configuration.saic_user}/vehicles/{message.vin}/info/lastMessage'
        self.publisher.publish_int(f'{message_prefix}/messageId', message.message_id)
        self.publisher.publish_str(f'{message_prefix}/messageType', message.message_type)
        self.publisher.publish_str(f'{message_prefix}/title', message.title)
        self.publisher.publish_str(f'{message_prefix}/messageTime', datetime_to_str(message.message_time))
        self.publisher.publish_str(f'{message_prefix}/sender', message.sender)
        if message.content is not None:
            self.publisher.publish_str(f'{message_prefix}/content', message.content)
        self.publisher.publish_str(f'{message_prefix}/status', message.get_read_status_str())
        self.publisher.publish_str(f'{message_prefix}/vin', message.vin)
        if message.vin is not None:
            handler = cast(VehicleHandler, self.vehicle_handler[message.vin])
            handler.force_update_by_message_time(message)

    def get_vehicle_handler(self, vin: str) -> VehicleHandler | None:
        if vin in self.vehicle_handler:
            return self.vehicle_handler[vin]
        else:
            logging.error(f'No vehicle handler found for VIN {vin}')
            return None

    def __on_refresh_mode_update(self, mode: str, vin: str):
        vehicle_handler = self.get_vehicle_handler(vin)
        if vehicle_handler is not None:
            if mode == 'force':
                vehicle_handler.force_update = True
                logging.info(f'Forcing single fetch for VIN {vin}. Refresh mode was: {vehicle_handler.refresh_mode}')
            else:
                vehicle_handler.refresh_mode = mode
                logging.info(f'Setting vehicle handler mode for VIN {vin} to refresh mode: {mode}')

    def __on_active_refresh_interval_update(self, seconds: int, vin: str):
        vehicle_handler = self.get_vehicle_handler(vin)
        if vehicle_handler is not None:
            vehicle_handler.set_active_refresh_interval(seconds)
            logging.info(f'Setting active query interval in vehicle handler for VIN {vin} to {seconds} seconds')

    def __on_inactive_refresh_interval_update(self, seconds: int, vin: str):
        vehicle_handler = self.get_vehicle_handler(vin)
        if vehicle_handler is not None:
            vehicle_handler.set_inactive_refresh_interval(seconds)
            logging.info(f'Setting inactive query interval in vehicle handler for VIN {vin} to {seconds} seconds')

    def __on_doors_lock_state_update(self, doors_locked: bool, vin: str):
        vehicle_handler = self.get_vehicle_handler(vin)
        if vehicle_handler is not None:
            vehicle_handler.update_doors_lock_state(doors_locked)

    def __on_rear_window_heat_state_update(self, rear_window_heat_state: str, vin: str):
        vehicle_handler = self.get_vehicle_handler(vin)
        if vehicle_handler is not None:
            vehicle_handler.update_rear_window_heat_state(rear_window_heat_state)

    def __on_front_window_heat_state_update(self, front_window_heat_state: str, vin: str):
        vehicle_handler = self.get_vehicle_handler(vin)
        if vehicle_handler is not None:
            vehicle_handler.update_front_window_heat_state(front_window_heat_state)

    def __on_ac_state_update(self, ac_state: str, vin: str):
        vehicle_handler = self.get_vehicle_handler(vin)
        if vehicle_handler is not None:
            vehicle_handler.update_ac_state(ac_state)

    def __on_lp_charging(self, vin: str, is_charging: bool):
        vehicle_handler = self.get_vehicle_handler(vin)
        if vehicle_handler is not None:
            vehicle_handler.is_charging_on_openwb = is_charging
            if is_charging:
                logging.info(f'Vehicle {vin} started charging on openWB.')
                vehicle_handler.force_update = True
            else:
                logging.info(f'Vehicle {vin} stopped charging on openWB.')
        else:
            logging.error(f'No vehicle handler found for VIN {vin}')

    def __on_publish_raw_value(self, key: str, raw: str):
        self.publisher.publish_str(key, raw)

    def __on_publish_json_value(self, key: str, json: dict):
        self.publisher.publish_json(key, json)

    def get_open_wb_lp(self, vin) -> str | None:
        for key in self.configuration.open_wb_lp_map.keys():
            if self.configuration.open_wb_lp_map[key] == vin:
                return key
        return None


class MessageHandler:
    def __init__(self, gateway: MqttGateway, saicapi: SaicApi):
        self.gateway = gateway
        self.saicapi = saicapi

    def polling(self):
        try:
            message_list = self.saicapi.get_message_list_with_retry()
            logging.info(f'{len(message_list)} messages received')

            latest_message = None
            latest_timestamp = None
            latest_vehicle_start_message = None
            latest_vehicle_start_timestamp = None
            for message in message_list:
                logging.info(message.get_details())

                if is_vehicle_start_message(message):
                    if latest_vehicle_start_message is None:
                        latest_vehicle_start_timestamp = message.message_time
                        latest_vehicle_start_message = message
                    elif latest_vehicle_start_timestamp < message.message_time:
                        latest_vehicle_start_timestamp = message.message_time
                        latest_vehicle_start_message = message
                # find the latest message
                if latest_timestamp is None:
                    latest_timestamp = message.message_time
                    latest_message = message
                elif latest_timestamp < message.message_time:
                    latest_timestamp = message.message_time
                    latest_message = message

            if latest_vehicle_start_message is not None:
                logging.info(f'{latest_vehicle_start_message.title} detected'
                             + f' at {latest_vehicle_start_message.message_time}')
                self.gateway.notify_message(latest_vehicle_start_message)
                # delete the vehicle start message after processing it
                try:
                    message_id = latest_vehicle_start_message.message_id
                    self.saicapi.delete_message(message_id)
                    logging.info(f'{latest_vehicle_start_message.title} message with ID {message_id} deleted')
                except SaicApiException as e:
                    logging.exception('Could not delete message from server', exc_info=e)
            elif latest_message is not None:
                self.gateway.notify_message(latest_message)
        except SaicApiException as e:
            logging.exception('MessageHandler poll loop failed', exc_info=e)


class EnvDefault(argparse.Action):
    def __init__(self, envvar, required=True, default=None, **kwargs):
        if (
                envvar in os.environ
                and os.environ[envvar]
        ):
            default = os.environ[envvar]
        if required and default:
            required = False
        super(EnvDefault, self).__init__(default=default, required=required, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)


async def periodic(message_handler: MessageHandler, query_messages_interval: int):
    while True:
        message_handler.polling()
        logging.debug(f'Waiting {query_messages_interval} seconds to check for new messages')
        await asyncio.sleep(float(query_messages_interval))


async def main(vh_map: dict, message_handler: MessageHandler, query_messages_interval: int):
    tasks = []
    for key in vh_map:
        logging.debug(f'Starting process for car {key}')
        vh = cast(VehicleHandler, vh_map[key])
        task = asyncio.create_task(vh.handle_vehicle(), name=f'handle_vehicle_{key}')
        tasks.append(task)

    tasks.append(asyncio.create_task(periodic(message_handler, query_messages_interval), name='message_handler'))

    await shutdown_handler(tasks)


async def shutdown_handler(tasks):
    while True:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task_name = task.get_name()
            if task.cancelled():
                logging.debug(f'{task_name !r} task was cancelled, this is only supposed if the application is '
                              f'shutting down')
            else:
                exception = task.exception()
                if exception is not None:
                    logging.exception(f'{task_name !r} task crashed with an exception', exc_info=exception)
                    raise SystemExit(-1)
                else:
                    logging.warning(f'{task_name !r} task terminated cleanly with result={task.result()}')
        if len(pending) == 0:
            break
        else:
            logging.warning(f'There are still {len(pending)} tasks... waiting for them to complete')


def process_arguments() -> Configuration:
    config = Configuration()
    parser = argparse.ArgumentParser(prog='MQTT Gateway')
    try:
        parser.add_argument('-m', '--mqtt-uri', help='The URI to the MQTT Server. Environment Variable: MQTT_URI,'
                                                     + 'TCP: tcp://mqtt.eclipseprojects.io:1883 '
                                                     + 'WebSocket: ws://mqtt.eclipseprojects.io:9001',
                            dest='mqtt_uri', required=True, action=EnvDefault, envvar='MQTT_URI')
        parser.add_argument('--mqtt-user', help='The MQTT user name. Environment Variable: MQTT_USER',
                            dest='mqtt_user', required=False, action=EnvDefault, envvar='MQTT_USER')
        parser.add_argument('--mqtt-password', help='The MQTT password. Environment Variable: MQTT_PASSWORD',
                            dest='mqtt_password', required=False, action=EnvDefault, envvar='MQTT_PASSWORD')
        parser.add_argument('--mqtt-topic-prefix', help='MQTT topic prefix. Environment Variable: MQTT_TOPIC'
                                                        + 'Default is saic', default='saic', dest='mqtt_topic',
                            required=False, action=EnvDefault, envvar='MQTT_TOPIC')
        parser.add_argument('-s', '--saic-uri', help='The SAIC uri. Environment Variable: SAIC_URI Default is the'
                                                     + ' European Production Endpoint: https://tap-eu.soimt.com',
                            default='https://tap-eu.soimt.com', dest='saic_uri', required=False, action=EnvDefault,
                            envvar='SAIC_URI')
        parser.add_argument('-u', '--saic-user',
                            help='The SAIC user name. Environment Variable: SAIC_USER', dest='saic_user', required=True,
                            action=EnvDefault, envvar='SAIC_USER')
        parser.add_argument('-p', '--saic-password', help='The SAIC password. Environment Variable: SAIC_PASSWORD',
                            dest='saic_password', required=True, action=EnvDefault, envvar='SAIC_PASSWORD')
        parser.add_argument('--abrp-api-key', help='The API key for the A Better Route Planer telemetry API.'
                                                   + ' Default is the open source telemetry'
                                                   + ' API key 8cfc314b-03cd-4efe-ab7d-4431cd8f2e2d.'
                                                   + ' Environment Variable: ABRP_API_KEY',
                            default='8cfc314b-03cd-4efe-ab7d-4431cd8f2e2d', dest='abrp_api_key', required=False,
                            action=EnvDefault, envvar='ABRP_API_KEY')
        parser.add_argument('--abrp-user-token', help='The mapping of VIN to ABRP User Token.'
                                                      + ' Multiple mappings can be provided seperated by ,'
                                                      + ' Example: LSJXXXX=12345-abcdef,LSJYYYY=67890-ghijkl,'
                                                      + ' Environment Variable: ABRP_USER_TOKEN',
                            dest='abrp_user_token', required=False, action=EnvDefault, envvar='ABRP_USER_TOKEN')
        parser.add_argument('--openwb-lp-map', help='The mapping of VIN to openWB charging point.'
                                                    + ' Multiple mappings can be provided seperated by ,'
                                                    + ' Example: LSJXXXX=1,LSJYYYY=2',
                            dest='open_wp_lp_map', required=False, action=EnvDefault, envvar='OPENWB_LP_MAP')
        parser.add_argument('--saic-relogin-delay', help='How long to wait before attempting another login to the SAIC '
                                                         'API. Environment Variable: SAIC_RELOGIN_DELAY',
                            dest='saic_relogin_delay', required=False, action=EnvDefault, envvar='SAIC_RELOGIN_DELAY',
                            type=check_positive)
        parser.add_argument('--ignore-vehicle-start-message-timestamp', help='Ignore message timestamps. Useful when the SAIC API '
                                                               'has a significant clock skew. Environment Variable: '
                                                               'IGNORE_VEHICLE_START_MESSAGE_TIMESTAMP',
                            dest='ignore_vehicle_start_message_timestamp', required=False, action=EnvDefault,
                            envvar='IGNORE_VEHICLE_START_MESSAGE_TIMESTAMP', type=str_to_bool, default=False)
        args = parser.parse_args()
        config.mqtt_user = args.mqtt_user
        config.mqtt_password = args.mqtt_password
        if args.saic_relogin_delay:
            config.saic_relogin_delay = args.saic_relogin_delay
        config.mqtt_topic = args.mqtt_topic
        config.saic_uri = args.saic_uri
        config.saic_user = args.saic_user
        config.saic_password = args.saic_password
        config.abrp_api_key = args.abrp_api_key
        if args.abrp_user_token:
            cfg_value_to_dict(args.abrp_user_token, config.abrp_token_map)
        if args.open_wp_lp_map:
            cfg_value_to_dict(args.open_wp_lp_map, config.open_wb_lp_map)
        config.saic_password = args.saic_password

        parse_result = urllib.parse.urlparse(args.mqtt_uri)
        if parse_result.scheme == 'tcp':
            config.mqtt_transport_protocol = 'tcp'
        elif parse_result.scheme == 'ws':
            config.mqtt_transport_protocol = 'websockets'
        else:
            raise SystemExit(f'Invalid MQTT URI scheme: {parse_result.scheme}, use tcp or ws')

        if not parse_result.port:
            if config.mqtt_transport_protocol == 'tcp':
                config.mqtt_port = 1883
            else:
                config.mqtt_port = 9001
        else:
            config.mqtt_port = parse_result.port

        config.mqtt_host = str(parse_result.hostname)

        config.ignore_vehicle_start_message_timestamp = args.ignore_vehicle_start_message_timestamp

        return config
    except argparse.ArgumentError as err:
        parser.print_help()
        SystemExit(err)


def cfg_value_to_dict(cfg_value: str, result_map: dict):
    if ',' in cfg_value:
        map_entries = cfg_value.split(',')
    else:
        map_entries = [cfg_value]

    for entry in map_entries:
        if '=' in entry:
            key_value_pair = entry.split('=')
            key = key_value_pair[0]
            value = key_value_pair[1]
            result_map[key] = value


def str_to_bool(value):
    lowercase_value = value.lower()
    if lowercase_value in {'false', 'f', '0', 'no', 'n'}:
        return False
    elif lowercase_value in {'true', 't', '1', 'yes', 'y'}:
        return True
    raise ValueError(f'{value} is not a valid boolean value')


def check_positive(value):
    ivalue = int(value)
    if ivalue <= 0:
        raise argparse.ArgumentTypeError(f'{ivalue} is an invalid positive int value')
    return ivalue


def is_vehicle_start_message(message):
    return message.message_type == '323'


if __name__ == '__main__':
    configuration = process_arguments()

    mqtt_gateway = MqttGateway(configuration)
    mqtt_gateway.run()
