import argparse
import asyncio
import datetime
import logging
import os
import time
import urllib.parse
from typing import cast

import paho.mqtt.client as mqtt

from home_assistant_discovery import HomeAssistantDiscovery
from saic_ismart_client.abrp_api import AbrpApi, AbrpApiException
from saic_ismart_client.common_model import TargetBatteryCode, ChargeCurrentLimitCode
from saic_ismart_client.ota_v1_1.data_model import VinInfo, MpUserLoggingInRsp, MpAlarmSettingType
from saic_ismart_client.ota_v2_1.data_model import OtaRvmVehicleStatusResp25857
from saic_ismart_client.ota_v3_0.data_model import OtaChrgMangDataResp
from saic_ismart_client.saic_api import SaicApi, SaicApiException, create_alarm_switch

import mqtt_topics
from Exceptions import MqttGatewayException
from configuration import Configuration
from mqtt_publisher import MqttClient
from publisher import Publisher
from vehicle import RefreshMode, VehicleState

MSG_CMD_SUCCESSFUL = 'Success'


def epoch_value_to_str(time_value: int) -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time_value))


def datetime_to_str(dt: datetime.datetime) -> str:
    return dt.strftime('%Y-%m-%d %H:%M:%S')


logging.basicConfig(format='%(asctime)s %(message)s')
LOG = logging.getLogger(__name__)
LOG.setLevel(level=os.getenv('LOG_LEVEL', 'INFO').upper())


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

    def update_front_window_heat_state(self, front_window_heat_state: str):
        result_key = f'{self.vehicle_prefix}/climate/frontWindowDefrosterHeating/result'
        try:
            if front_window_heat_state.lower() == 'on':
                LOG.info('Front window heating will be switched on')
                self.saic_api.start_front_defrost(self.vin_info)
                self.publisher.publish_str(result_key, MSG_CMD_SUCCESSFUL)
            elif front_window_heat_state.lower() == 'off':
                LOG.info('Front window heating will be switched off')
                self.saic_api.stop_front_defrost(self.vin_info)
                self.publisher.publish_str(result_key, MSG_CMD_SUCCESSFUL)
            else:
                message = f'Invalid front window heat state: {front_window_heat_state}. Valid values are on and off'
                self.publisher.publish_str(result_key, message)
        except SaicApiException as e:
            self.publisher.publish_str(result_key, f'Failed: {e.message}')
            LOG.exception('update_front_window_heat_state failed', exc_info=e)

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
                    and self.configuration.ha_discovery_enabled
            ):
                self.ha_discovery.publish_ha_discovery_messages()
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
            else:
                # car not active, wait a second
                await asyncio.sleep(1.0)

    def update_vehicle_status(self) -> OtaRvmVehicleStatusResp25857:
        vehicle_status_rsp_msg = self.saic_api.get_vehicle_status_with_retry(self.vin_info)
        vehicle_status_response = cast(OtaRvmVehicleStatusResp25857, vehicle_status_rsp_msg.application_data)
        self.vehicle_state.handle_vehicle_status(vehicle_status_response)

        return vehicle_status_response

    def update_charge_status(self) -> OtaChrgMangDataResp:
        chrg_mgmt_data_rsp_msg = self.saic_api.get_charging_status_with_retry(self.vin_info)
        charge_mgmt_data = cast(OtaChrgMangDataResp, chrg_mgmt_data_rsp_msg.application_data)
        self.vehicle_state.handle_charge_status(charge_mgmt_data)

        return charge_mgmt_data

    def handle_mqtt_command(self, msg: mqtt.MQTTMessage):
        topic = self.get_topic_without_vehicle_prefix(msg.topic)
        try:
            if msg.retain:
                raise MqttGatewayException('Message may not be retained')

            match topic:
                case mqtt_topics.DRIVETRAIN_HV_BATTERY_ACTIVE:
                    match msg.payload.decode().strip().lower():
                        case 'true':
                            self.vehicle_state.set_hv_battery_active(True)
                        case 'false':
                            self.vehicle_state.set_hv_battery_active(False)
                        case _:
                            raise MqttGatewayException(f'Unsupported payload {msg.payload.decode()}')
                case mqtt_topics.DRIVETRAIN_CHARGING:
                    match msg.payload.decode().strip().lower():
                        case 'true':
                            self.saic_api.start_charging_with_retry(self.vin_info)
                        case 'false':
                            self.saic_api.control_charging(True, self.vin_info)
                        case _:
                            raise MqttGatewayException(f'Unsupported payload {msg.payload.decode()}')
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
                            self.saic_api.start_ac(self.vin_info)
                        case 'front':
                            self.saic_api.start_ac_blowing(self.vin_info)
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
                            raw_charge_current_limit = str(payload)
                            charge_current_limit = ChargeCurrentLimitCode.to_code(raw_charge_current_limit)
                            self.saic_api.set_target_battery_soc(self.vehicle_state.target_soc, self.vin_info, charge_current_limit)
                            self.vehicle_state.update_charge_current_limit(charge_current_limit)
                        except ValueError:
                            raise MqttGatewayException(f'Error setting value for payload {payload}')
                    else:
                        logging.info(f'Unknown Target SOC: waiting for state update before changing charge current limit')
                        raise MqttGatewayException(f'Error setting charge current limit - SOC {self.vehicle_state.target_soc}')
                case mqtt_topics.DRIVETRAIN_SOC_TARGET:
                    payload = msg.payload.decode().strip()
                    try:
                        target_battery_code = TargetBatteryCode.from_percentage(int(payload))
                        self.vehicle_state.update_target_soc(target_battery_code)
                        self.saic_api.set_target_battery_soc(target_battery_code, self.vin_info)
                    except ValueError as e:
                        raise MqttGatewayException(f'Error setting SoC target: {e}')
                case _:
                    # set mode, period (in)-active,...
                    self.vehicle_state.configure_by_message(topic, msg)
            self.publisher.publish_str(f'{self.vehicle_prefix}/{topic}/result', 'Success')
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
        self.saic_api = SaicApi(config.saic_uri, config.saic_user, config.saic_password, config.saic_relogin_delay)
        self.saic_api.on_publish_json_value = self.__on_publish_json_value
        self.saic_api.on_publish_raw_value = self.__on_publish_raw_value
        self.publisher.connect()

    def run(self):
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
            wb_lp = self.get_open_wb_lp(vin_info.vin)
            if wb_lp:
                wallbox_soc_topic = f'{self.configuration.open_wb_topic}/set/lp/{wb_lp}/%Soc'
                LOG.debug(f'SoC for wallbox is published over MQTT topic: {wallbox_soc_topic}')
            else:
                wallbox_soc_topic = ''
            vehicle_state = VehicleState(self.publisher, account_prefix, vin_info.vin, wallbox_soc_topic)
            vehicle_state.configure(vin_info)

            vehicle_handler = VehicleHandler(
                self.configuration,  # Gateway pointer
                self.saic_api,
                self.publisher,
                vin_info,
                vehicle_state)
            self.vehicle_handler[vin_info.vin] = vehicle_handler

        message_handler = MessageHandler(self, self.saic_api, self.configuration.messages_request_interval)
        asyncio.run(main(self.vehicle_handler, message_handler))

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

    def __on_publish_json_value(self, key: str, json: dict):
        self.publisher.publish_json(key, json)

    def get_open_wb_lp(self, vin) -> str | None:
        for key in self.configuration.open_wb_lp_map.keys():
            if self.configuration.open_wb_lp_map[key] == vin:
                return key
        return None


class MessageHandler:
    def __init__(self, gateway: MqttGateway, saicapi: SaicApi, refresh_interval: int):
        self.gateway = gateway
        self.saicapi = saicapi
        self.refresh_interval = refresh_interval

    async def check_for_new_messages(self) -> None:
        while True:
            if self.__should_poll():
                LOG.debug("Checking for new messages")
                self.__polling()
            else:
                LOG.debug("Not checking for new messages since all cars have RefreshMode.OFF")
            LOG.debug(f'Waiting {self.refresh_interval} seconds to check for new messages')
            await asyncio.sleep(float(self.refresh_interval))

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


async def main(vh_map: dict[str, VehicleHandler], message_handler: MessageHandler):
    tasks = []
    for key in vh_map:
        LOG.debug(f'Starting process for car {key}')
        vh = vh_map[key]
        task = asyncio.create_task(vh.handle_vehicle(), name=f'handle_vehicle_{key}')
        tasks.append(task)

    tasks.append(asyncio.create_task(message_handler.check_for_new_messages(), name='message_handler'))

    await shutdown_handler(tasks)


async def shutdown_handler(tasks):
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
        parser.add_argument('--ha-discovery', help='Enable Home Assistant Discovery. Environment Variable: '
                                                   'HA_DISCOVERY_ENABLED', dest='ha_discovery_enabled', required=False,
                            action=EnvDefault,
                            envvar='HA_DISCOVERY_ENABLED', default=True, type=check_bool)
        parser.add_argument('--ha-discovery-prefix', help='Home Assistant Discovery Prefix. Environment Variable: '
                                                          'HA_DISCOVERY_PREFIX', dest='ha_discovery_prefix',
                            required=False, action=EnvDefault,
                            envvar='HA_DISCOVERY_PREFIX', default='homeassistant')
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


def check_positive(value):
    ivalue = int(value)
    if ivalue <= 0:
        raise argparse.ArgumentTypeError(f'{ivalue} is an invalid positive int value')
    return ivalue


def check_bool(value):
    return str(value).lower() in ['true', '1', 'yes', 'y']


if __name__ == '__main__':
    configuration = process_arguments()

    mqtt_gateway = MqttGateway(configuration)
    mqtt_gateway.run()
