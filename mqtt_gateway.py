import argparse
import asyncio
import datetime
import faulthandler
import json
import logging
import os
import signal
import sys
import time
import urllib.parse
from typing import Callable, cast

import apscheduler.schedulers.asyncio
import paho.mqtt.client as mqtt
from saic_ismart_client.exceptions import SaicApiException

from charging_station import ChargingStation
from home_assistant_discovery import HomeAssistantDiscovery
from saic_ismart_client.abrp_api import AbrpApi, AbrpApiException
from saic_ismart_client.common_model import TargetBatteryCode, ChargeCurrentLimitCode, ScheduledChargingMode
from saic_ismart_client.ota_v1_1.data_model import VinInfo, MpUserLoggingInRsp, MpAlarmSettingType
from saic_ismart_client.ota_v2_1.data_model import OtaRvmVehicleStatusResp25857
from saic_ismart_client.ota_v3_0.data_model import OtaChrgMangDataResp
from saic_ismart_client.saic_api import SaicApi, create_alarm_switch

import mqtt_topics
from Exceptions import MqttGatewayException
from configuration import Configuration
from mqtt_publisher import MqttClient
from publisher import Publisher
from vehicle import RefreshMode, VehicleState

MSG_CMD_SUCCESSFUL = 'Success'
CHARGING_STATIONS_FILE = 'charging-stations.json'


def epoch_value_to_str(time_value: int) -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time_value))


def datetime_to_str(dt: datetime.datetime) -> str:
    return dt.strftime('%Y-%m-%d %H:%M:%S')


logging.root.handlers = []
logging.basicConfig(format='{asctime:s} [{levelname:^8s}] {message:s} - {name:s}', style='{')
LOG = logging.getLogger(__name__)
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
LOG.setLevel(level=LOG_LEVEL)
logging.getLogger('apscheduler').setLevel(level=LOG_LEVEL)


def debug_log_enabled():
    return LOG_LEVEL == 'DEBUG'


class VehicleHandler:
    def __init__(self, config: Configuration, saicapi: SaicApi, publisher: Publisher, vin_info: VinInfo,
                 vehicle_state: VehicleState):
        self.configuration = config
        self.saic_api = saicapi
        self.publisher = publisher
        self.vin_info = vin_info
        self.vehicle_prefix = f'{self.configuration.saic_user}/vehicles/{self.vin_info.vin}'
        self.vehicle_state = vehicle_state
        self.ha_discovery = HomeAssistantDiscovery(vehicle_state, vin_info)
        if vin_info.vin in self.configuration.abrp_token_map:
            abrp_user_token = self.configuration.abrp_token_map[vin_info.vin]
        else:
            abrp_user_token = None
        self.abrp_api = AbrpApi(self.configuration.abrp_api_key, abrp_user_token)

    async def handle_vehicle(self) -> None:
        self.vehicle_state.configure(self.vin_info)
        start_time = datetime.datetime.now()
        self.vehicle_state.notify_car_activity_time(start_time, True)

        while True:
            if (
                    not self.vehicle_state.is_complete()
                    and datetime.datetime.now() > start_time + datetime.timedelta(seconds=10)
            ):
                self.vehicle_state.configure_missing()
            if (
                    self.vehicle_state.is_complete()
                    and self.vehicle_state.should_refresh()
            ):
                try:
                    vehicle_status = self.update_vehicle_status()
                    charge_status = self.update_charge_status()
                    abrp_response = self.abrp_api.update_abrp(vehicle_status, charge_status)
                    self.publisher.publish_str(f'{self.vehicle_prefix}/{mqtt_topics.INTERNAL_ABRP}', abrp_response)
                    self.vehicle_state.mark_successful_refresh()
                    LOG.info('Refreshing vehicle status succeeded...')
                except SaicApiException as e:
                    LOG.exception('handle_vehicle loop failed during SAIC API call', exc_info=e)
                    await asyncio.sleep(float(30))
                except AbrpApiException as ae:
                    LOG.exception('handle_vehicle loop failed during ABRP API call', exc_info=ae)
                finally:
                    if self.configuration.ha_discovery_enabled:
                        self.ha_discovery.publish_ha_discovery_messages()
            else:
                # car not active, wait a second
                await asyncio.sleep(1.0)

    def update_vehicle_status(self) -> OtaRvmVehicleStatusResp25857:
        LOG.info('Updating vehicle status')
        vehicle_status_rsp_msg = self.saic_api.get_vehicle_status_with_retry(self.vin_info)
        vehicle_status_response = cast(OtaRvmVehicleStatusResp25857, vehicle_status_rsp_msg.application_data)
        self.vehicle_state.handle_vehicle_status(vehicle_status_response)

        return vehicle_status_response

    def update_charge_status(self) -> OtaChrgMangDataResp:
        LOG.info('Updating charging status')
        chrg_mgmt_data_rsp_msg = self.saic_api.get_charging_status_with_retry(self.vin_info)
        charge_mgmt_data = cast(OtaChrgMangDataResp, chrg_mgmt_data_rsp_msg.application_data)
        self.vehicle_state.handle_charge_status(charge_mgmt_data)

        return charge_mgmt_data

    def handle_mqtt_command(self, msg: mqtt.MQTTMessage):
        topic = self.get_topic_without_vehicle_prefix(msg.topic)
        try:
            if msg.retain:
                raise MqttGatewayException(
                    f'Message may not be retained but received a retained message on topic {topic}'
                )

            match topic:
                case mqtt_topics.DRIVETRAIN_HV_BATTERY_ACTIVE:
                    match msg.payload.decode().strip().lower():
                        case 'true':
                            LOG.info("HV battery is now active")
                            self.vehicle_state.set_hv_battery_active(True)
                        case 'false':
                            LOG.info("HV battery is now inactive")
                            self.vehicle_state.set_hv_battery_active(False)
                        case _:
                            raise MqttGatewayException(f'Unsupported payload {msg.payload.decode()}')
                case mqtt_topics.DRIVETRAIN_CHARGING:
                    match msg.payload.decode().strip().lower():
                        case 'true':
                            LOG.info("Charging will be started")
                            self.saic_api.start_charging_with_retry(self.vin_info)
                        case 'false':
                            LOG.info("Charging will be stopped")
                            self.saic_api.control_charging(True, self.vin_info)
                        case _:
                            raise MqttGatewayException(f'Unsupported payload {msg.payload.decode()}')
                case mqtt_topics.CLIMATE_REMOTE_TEMPERATURE:
                    payload = msg.payload.decode().strip()
                    try:
                        LOG.info("Setting remote climate target temperature to %s", payload)
                        temp = int(payload)
                        changed = self.vehicle_state.set_ac_temperature(temp)
                        if changed and self.vehicle_state.is_remote_ac_running():
                            self.saic_api.start_ac(self.vin_info,
                                                   temperature_idx=self.vehicle_state.get_ac_temperature_idx())

                    except ValueError as e:
                        raise MqttGatewayException(f'Error setting SoC target: {e}')
                case mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE:
                    match msg.payload.decode().strip().lower():
                        case 'off':
                            LOG.info('A/C will be switched off')
                            self.saic_api.stop_ac(self.vin_info)
                        case 'blowingOnly':
                            LOG.info('A/C will be set to blowing only')
                            self.saic_api.start_ac_blowing(self.vin_info)
                        case 'on':
                            LOG.info('A/C will be switched on')
                            self.saic_api.start_ac(self.vin_info,
                                                   temperature_idx=self.vehicle_state.get_ac_temperature_idx())
                        case 'front':
                            LOG.info("A/C will be set to front seats only")
                            self.saic_api.start_ac_blowing(self.vin_info)
                        case _:
                            raise MqttGatewayException(f'Unsupported payload {msg.payload.decode()}')
                case mqtt_topics.DOORS_BOOT:
                    match msg.payload.decode().strip().lower():
                        case 'true':
                            LOG.info(f'We cannot lock vehicle {self.vin_info.vin} boot remotely')
                        case 'false':
                            LOG.info(f'Vehicle {self.vin_info.vin} boot will be unlocked')
                            self.saic_api.open_tailgate(self.vin_info)
                        case _:
                            raise MqttGatewayException(f'Unsupported payload {msg.payload.decode()}')
                case mqtt_topics.DOORS_LOCKED:
                    match msg.payload.decode().strip().lower():
                        case 'true':
                            LOG.info(f'Vehicle {self.vin_info.vin} will be locked')
                            self.saic_api.lock_vehicle(self.vin_info)
                        case 'false':
                            LOG.info(f'Vehicle {self.vin_info.vin} will be unlocked')
                            self.saic_api.unlock_vehicle(self.vin_info)
                        case _:
                            raise MqttGatewayException(f'Unsupported payload {msg.payload.decode()}')
                case mqtt_topics.CLIMATE_BACK_WINDOW_HEAT:
                    match msg.payload.decode().strip().lower():
                        case 'off':
                            LOG.info('Rear window heating will be switched off')
                            self.saic_api.stop_rear_window_heat(self.vin_info)
                        case 'on':
                            LOG.info('Rear window heating will be switched on')
                            self.saic_api.start_rear_window_heat(self.vin_info)
                        case _:
                            raise MqttGatewayException(f'Unsupported payload {msg.payload.decode()}')
                case mqtt_topics.CLIMATE_FRONT_WINDOW_HEAT:
                    match msg.payload.decode().strip().lower():
                        case 'off':
                            LOG.info('Front window heating will be switched off')
                            self.saic_api.stop_front_defrost(self.vin_info)
                        case 'on':
                            LOG.info('Front window heating will be switched on')
                            self.saic_api.start_front_defrost(self.vin_info)
                        case _:
                            raise MqttGatewayException(f'Unsupported payload {msg.payload.decode()}')
                case mqtt_topics.DRIVETRAIN_CHARGECURRENT_LIMIT:
                    payload = msg.payload.decode().strip().upper()
                    if self.vehicle_state.target_soc is not None:
                        try:
                            LOG.info("Setting charging current limit to %s", payload)
                            raw_charge_current_limit = str(payload)
                            charge_current_limit = ChargeCurrentLimitCode.to_code(raw_charge_current_limit)
                            self.saic_api.set_target_battery_soc(self.vehicle_state.target_soc, self.vin_info,
                                                                 charge_current_limit)
                            self.vehicle_state.update_charge_current_limit(charge_current_limit)
                        except ValueError:
                            raise MqttGatewayException(f'Error setting value for payload {payload}')
                    else:
                        logging.info(
                            f'Unknown Target SOC: waiting for state update before changing charge current limit')
                        raise MqttGatewayException(
                            f'Error setting charge current limit - SOC {self.vehicle_state.target_soc}')
                case mqtt_topics.DRIVETRAIN_SOC_TARGET:
                    payload = msg.payload.decode().strip()
                    try:
                        LOG.info("Setting SoC target to %s", payload)
                        target_battery_code = TargetBatteryCode.from_percentage(int(payload))
                        self.saic_api.set_target_battery_soc(target_battery_code, self.vin_info)
                        self.vehicle_state.update_target_soc(target_battery_code)
                    except ValueError as e:
                        raise MqttGatewayException(f'Error setting SoC target: {e}')
                case mqtt_topics.DRIVETRAIN_CHARGING_SCHEDULE:
                    payload = msg.payload.decode().strip()
                    try:
                        LOG.info("Setting charging schedule to %s", payload)
                        payload_json = json.loads(payload)
                        start_time = datetime.time.fromisoformat(payload_json['startTime'])
                        end_time = datetime.time.fromisoformat(payload_json['endTime'])
                        mode = ScheduledChargingMode[payload_json['mode'].upper()]
                        self.saic_api.set_schedule_charging(start_time, end_time, mode, self.vin_info)
                        self.vehicle_state.update_scheduled_charging(start_time, mode)
                    except Exception as e:
                        raise MqttGatewayException(f'Error setting charging schedule: {e}')
                case _:
                    # set mode, period (in)-active,...
                    self.vehicle_state.configure_by_message(topic, msg)
            self.publisher.publish_str(f'{self.vehicle_prefix}/{topic}/result', 'Success')
            self.vehicle_state.set_refresh_mode(RefreshMode.FORCE)
        except MqttGatewayException as e:
            self.publisher.publish_str(f'{self.vehicle_prefix}/{topic}/result', f'Failed: {e.message}')
            LOG.exception(e.message, exc_info=e)
        except SaicApiException as se:
            self.publisher.publish_str(f'{self.vehicle_prefix}/{topic}/result', f'Failed: {se.message}')
            LOG.exception(se.message, exc_info=se)

    def get_topic_without_vehicle_prefix(self, topic: str) -> str:
        global_topic_removed = topic[len(self.configuration.mqtt_topic) + 1:]
        elements = global_topic_removed.split('/')
        result = ''
        for i in range(3, len(elements) - 1):
            result += f'/{elements[i]}'
        return result[1:]


class MqttGateway:
    def __init__(self, config: Configuration):
        self.configuration = config
        self.vehicle_handler: dict[str, VehicleHandler] = {}
        self.publisher = MqttClient(self.configuration)
        self.publisher.on_mqtt_command_received = self.__on_mqtt_command_received
        self.saic_api = SaicApi(
            config.saic_uri,
            config.saic_rest_uri,
            config.saic_user,
            config.saic_password,
            config.saic_relogin_delay
        )
        self.saic_api.on_publish_json_value = self.__on_publish_json_value
        self.saic_api.on_publish_raw_value = self.__on_publish_raw_value
        self.publisher.connect()

    async def run(self):
        scheduler = apscheduler.schedulers.asyncio.AsyncIOScheduler()
        scheduler.start()
        try:
            login_response_message = self.saic_api.login()
            user_logging_in_response = cast(MpUserLoggingInRsp, login_response_message.application_data)
        except SaicApiException as e:
            LOG.exception('MqttGateway crashed due to SaicApiException', exc_info=e)
            raise SystemExit(e)

        for alarm_setting_type in MpAlarmSettingType:
            try:
                alarm_switches = [create_alarm_switch(alarm_setting_type)]
                self.saic_api.set_alarm_switches(alarm_switches)
                LOG.info(f'Registering for {alarm_setting_type.value} messages')
            except SaicApiException:
                LOG.warning(f'Failed to register for {alarm_setting_type.value} messages')

        for info in user_logging_in_response.vin_list:
            vin_info = cast(VinInfo, info)
            account_prefix = f'{self.configuration.saic_user}/{mqtt_topics.VEHICLES}/{vin_info.vin}'
            charging_station = self.get_charging_station(vin_info.vin)
            if charging_station:
                LOG.debug(f'SoC for charging station will be published over MQTT topic: {charging_station.soc_topic}')
            total_battery_capacity = configuration.battery_capacity_map.get(vin_info.vin, None)
            vehicle_state = VehicleState(
                self.publisher,
                scheduler,
                account_prefix,
                vin_info,
                charging_station,
                charge_polling_min_percent=self.configuration.charge_dynamic_polling_min_percentage,
                total_battery_capacity=total_battery_capacity
            )
            vehicle_state.configure(vin_info)

            vehicle_handler = VehicleHandler(
                self.configuration,
                self.saic_api,
                self.publisher,  # Gateway pointer
                vin_info,
                vehicle_state
            )
            self.vehicle_handler[vin_info.vin] = vehicle_handler
        message_handler = MessageHandler(self, self.saic_api)
        scheduler.add_job(
            func=message_handler.check_for_new_messages,
            trigger='interval',
            seconds=self.configuration.messages_request_interval,
            id='message_handler',
            name='Check for new messages',
            max_instances=1
        )
        await self.__main_loop()

    def get_vehicle_handler(self, vin: str) -> VehicleHandler | None:
        if vin in self.vehicle_handler:
            return self.vehicle_handler[vin]
        else:
            LOG.error(f'No vehicle handler found for VIN {vin}')
            return None

    def __on_mqtt_command_received(self, vin: str, msg: mqtt.MQTTMessage) -> None:
        vehicle_handler = self.get_vehicle_handler(vin)
        if vehicle_handler:
            vehicle_handler.handle_mqtt_command(msg)
        else:
            LOG.debug(f'Command for unknown vin {vin} received')

    def __on_publish_raw_value(self, key: str, raw: str):
        self.publisher.publish_str(key, raw)

    def __on_publish_json_value(self, key: str, json_data: dict):
        self.publisher.publish_json(key, json_data)

    def get_charging_station(self, vin) -> ChargingStation | None:
        if vin in self.configuration.charging_stations_by_vin:
            return self.configuration.charging_stations_by_vin[vin]
        else:
            return None

    async def __main_loop(self):
        tasks = []
        for (key, vh) in self.vehicle_handler.items():
            LOG.debug(f'Starting process for car {key}')
            task = asyncio.create_task(vh.handle_vehicle(), name=f'handle_vehicle_{key}')
            tasks.append(task)

        await self.__shutdown_handler(tasks)

    @staticmethod
    async def __shutdown_handler(tasks):
        while True:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task_name = task.get_name()
                if task.cancelled():
                    LOG.debug(f'{task_name !r} task was cancelled, this is only supposed if the application is '
                              + f'shutting down')
                else:
                    exception = task.exception()
                    if exception is not None:
                        LOG.exception(f'{task_name !r} task crashed with an exception', exc_info=exception)
                        raise SystemExit(-1)
                    else:
                        LOG.warning(f'{task_name !r} task terminated cleanly with result={task.result()}')
            if len(pending) == 0:
                break
            else:
                LOG.warning(f'There are still {len(pending)} tasks... waiting for them to complete')


class MessageHandler:
    def __init__(self, gateway: MqttGateway, saicapi: SaicApi):
        self.gateway = gateway
        self.saicapi = saicapi

    async def check_for_new_messages(self) -> None:
        if self.__should_poll():
            LOG.debug("Checking for new messages")
            self.__polling()
        else:
            LOG.debug("Not checking for new messages since all cars have RefreshMode.OFF")

    def __polling(self):
        try:
            message_list = self.saicapi.get_message_list_with_retry()
            LOG.info(f'{len(message_list)} messages received')

            latest_message = None
            latest_timestamp = None
            latest_vehicle_start_message = None
            latest_vehicle_start_timestamp = None
            for message in message_list:
                LOG.info(message.get_details())

                if message.message_type == '323':
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
                LOG.info(f'{latest_vehicle_start_message.title} detected'
                         + f' at {latest_vehicle_start_message.message_time}')
                vehicle_handler = self.gateway.get_vehicle_handler(latest_vehicle_start_message.vin)
                if vehicle_handler:
                    vehicle_handler.vehicle_state.notify_message(latest_vehicle_start_message)
                # delete the vehicle start message after processing it
                try:
                    message_id = latest_vehicle_start_message.message_id
                    self.saicapi.delete_message(message_id)
                    LOG.info(f'{latest_vehicle_start_message.title} message with ID {message_id} deleted')
                except SaicApiException as e:
                    LOG.exception('Could not delete message from server', exc_info=e)
            elif latest_message is not None:
                vehicle_handler = self.gateway.get_vehicle_handler(latest_message.vin)
                if vehicle_handler:
                    vehicle_handler.vehicle_state.notify_message(latest_message)
        except SaicApiException as e:
            LOG.exception('MessageHandler poll loop failed', exc_info=e)

    def __should_poll(self):
        vehicle_handlers = self.gateway.vehicle_handler or dict()
        refresh_modes = [
            vh.vehicle_state.refresh_mode
            for vh in vehicle_handlers.values()
            if vh.vehicle_state is not None
        ]
        # We do not poll if we have no cars or all cars have RefreshMode.OFF
        if len(refresh_modes) == 0 or all(mode == RefreshMode.OFF for mode in refresh_modes):
            return False
        else:
            return True


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


def get_charging_stations(open_wb_lp_map: dict[str, str]) -> dict[str, ChargingStation]:
    LOG.info(f'OPENWB_LP_MAP is deprecated! Please provide {CHARGING_STATIONS_FILE} file instead!')
    charging_stations = {}
    for loading_point_no in open_wb_lp_map.keys():
        vin = open_wb_lp_map[loading_point_no]
        charging_station = ChargingStation(vin, f'openWB/lp/{loading_point_no}/boolChargeStat', '1',
                                           f'openWB/set/lp/{loading_point_no}/%Soc')
        charging_stations[vin] = charging_station

    return charging_stations


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
        parser.add_argument('--mqtt-client-id', help='The MQTT Client Identifier. Environment Variable: '
                                                     + 'MQTT_CLIENT_ID '
                                                     + 'Default is saic-python-mqtt-gateway',
                            default='saic-python-mqtt-gateway', dest='mqtt_client_id', required=False,
                            action=EnvDefault, envvar='MQTT_CLIENT_ID')
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
        parser.add_argument('--battery-capacity-mapping', help='The mapping of VIN to full batteryc'
                                                               + ' apacity. Multiple mappings can be provided separated'
                                                               + ' by , Example: LSJXXXX=54.0,LSJYYYY=64.0,'
                                                               + ' Environment Variable: BATTERY_CAPACITY_MAPPING',
                            dest='battery_capacity_mapping', required=False, action=EnvDefault,
                            envvar='BATTERY_CAPACITY_MAPPING')
        parser.add_argument('--openwb-lp-map', help='The mapping of VIN to openWB charging point.'
                                                    + ' Multiple mappings can be provided seperated by ,'
                                                    + ' Example: LSJXXXX=1,LSJYYYY=2',
                            dest='open_wp_lp_map', required=False, action=EnvDefault, envvar='OPENWB_LP_MAP')
        parser.add_argument('--charging-stations-json', help='Custom charging stations configuration file name',
                            dest='charging_stations_file', required=False, action=EnvDefault,
                            envvar='CHARGING_STATIONS_JSON')
        parser.add_argument('--saic-relogin-delay', help='How long to wait before attempting another login to the SAIC '
                                                         'API. Environment Variable: SAIC_RELOGIN_DELAY',
                            dest='saic_relogin_delay', required=False, action=EnvDefault, envvar='SAIC_RELOGIN_DELAY',
                            type=check_positive)
        parser.add_argument('--ha-discovery', help='Enable Home Assistant Discovery. Environment Variable: '
                                                   'HA_DISCOVERY_ENABLED', dest='ha_discovery_enabled', required=False,
                            action=EnvDefault,
                            envvar='HA_DISCOVERY_ENABLED', default=True, type=check_bool)
        parser.add_argument('--ha-discovery-prefix', help='Home Assistant Discovery Prefix. Environment Variable: '
                                                          'HA_DISCOVERY_PREFIX', dest='ha_discovery_prefix',
                            required=False, action=EnvDefault,
                            envvar='HA_DISCOVERY_PREFIX', default='homeassistant')
        parser.add_argument('--charge-min-percentage',
                            help='How many % points we should try to refresh the charge state. Environment Variable: '
                                 'CHARGE_MIN_PERCENTAGE', dest='charge_dynamic_polling_min_percentage', required=False,
                            action=EnvDefault, envvar='CHARGE_MIN_PERCENTAGE', default='1.0', type=check_positive_float)

        args = parser.parse_args()
        config.mqtt_user = args.mqtt_user
        config.mqtt_password = args.mqtt_password
        config.mqtt_client_id = args.mqtt_client_id
        config.charge_dynamic_polling_min_percentage = args.charge_dynamic_polling_min_percentage
        if args.saic_relogin_delay:
            config.saic_relogin_delay = args.saic_relogin_delay
        config.mqtt_topic = args.mqtt_topic
        config.saic_uri = args.saic_uri
        config.saic_user = args.saic_user
        config.saic_password = args.saic_password
        config.abrp_api_key = args.abrp_api_key
        if args.abrp_user_token:
            cfg_value_to_dict(args.abrp_user_token, config.abrp_token_map)
        if args.battery_capacity_mapping:
            cfg_value_to_dict(
                args.battery_capacity_mapping,
                config.battery_capacity_map,
                value_type=check_positive_float
            )
        if args.open_wp_lp_map:
            open_wb_lp_map = {}
            cfg_value_to_dict(args.open_wp_lp_map, open_wb_lp_map)
            config.charging_stations_by_vin = get_charging_stations(open_wb_lp_map)
        if args.charging_stations_file:
            process_charging_stations_file(config, args.charging_stations_file)
        else:
            process_charging_stations_file(config, f'./{CHARGING_STATIONS_FILE}')

        config.saic_password = args.saic_password

        if args.ha_discovery_enabled:
            config.ha_discovery_enabled = args.ha_discovery_enabled

        if args.ha_discovery_prefix:
            config.ha_discovery_prefix = args.ha_discovery_prefix

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

        return config
    except argparse.ArgumentError as err:
        parser.print_help()
        SystemExit(err)


def process_charging_stations_file(config: Configuration, json_file: str):
    try:
        with open(json_file, 'r') as f:
            data = json.load(f)

            for item in data:
                charge_state_topic = item['chargeStateTopic']
                charging_value = item['chargingValue']
                soc_topic = item['socTopic']
                vin = item['vin']
                charging_station = ChargingStation(vin, charge_state_topic, charging_value, soc_topic)
                if 'chargerConnectedTopic' in item:
                    charging_station.connected_topic = item['chargerConnectedTopic']
                if 'chargerConnectedValue' in item:
                    charging_station.connected_value = item['chargerConnectedValue']
                config.charging_stations_by_vin[vin] = charging_station
    except FileNotFoundError:
        LOG.warning(f'File {json_file} does not exist')
    except json.JSONDecodeError as e:
        LOG.exception(f'Reading {json_file} failed', exc_info=e)


def cfg_value_to_dict(cfg_value: str, result_map: dict, value_type: Callable[[str], any] = str):
    if ',' in cfg_value:
        map_entries = cfg_value.split(',')
    else:
        map_entries = [cfg_value]

    for entry in map_entries:
        if '=' in entry:
            key_value_pair = entry.split('=')
            key = key_value_pair[0]
            value = key_value_pair[1]
            result_map[key] = value_type(value)


def check_positive(value):
    ivalue = int(value)
    if ivalue <= 0:
        raise argparse.ArgumentTypeError(f'{ivalue} is an invalid positive int value')
    return ivalue


def check_positive_float(value):
    fvalue = float(value)
    if fvalue <= 0:
        raise argparse.ArgumentTypeError(f'{fvalue} is an invalid positive float value')
    return fvalue


def check_bool(value):
    return str(value).lower() in ['true', '1', 'yes', 'y']


if __name__ == '__main__':
    # Enable fault handler to get a thread dump on SIGQUIT
    faulthandler.enable(file=sys.stderr, all_threads=True)
    if hasattr(faulthandler, 'register'):
        faulthandler.register(signal.SIGQUIT, chain=False)
    configuration = process_arguments()

    mqtt_gateway = MqttGateway(configuration)
    asyncio.run(mqtt_gateway.run(), debug=debug_log_enabled())
