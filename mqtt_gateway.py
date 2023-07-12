import argparse
import asyncio
import datetime
import logging
import os
import time
import urllib.parse
from typing import cast

import paho.mqtt.client as mqtt
from saic_ismart_client.abrp_api import AbrpApi, AbrpApiException
from saic_ismart_client.ota_v1_1.data_model import VinInfo, MpUserLoggingInRsp, MpAlarmSettingType
from saic_ismart_client.ota_v2_1.data_model import OtaRvmVehicleStatusResp25857
from saic_ismart_client.ota_v3_0.data_model import OtaChrgMangDataResp
from saic_ismart_client.saic_api import SaicApi, SaicApiException, TargetBatteryCode, create_alarm_switch

import mqtt_topics
from Exceptions import MqttGatewayException
from configuration import Configuration
from mqtt_publisher import MqttClient
from publisher import Publisher
from vehicle import VehicleState

MSG_CMD_SUCCESSFUL = 'Success'


def epoch_value_to_str(time_value: int) -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time_value))


def datetime_to_str(dt: datetime.datetime) -> str:
    return dt.strftime('%Y-%m-%d %H:%M:%S')


logging.basicConfig(format='%(asctime)s %(message)s')
logging.getLogger().setLevel(level=os.getenv('LOG_LEVEL', 'INFO').upper())


class VehicleHandler:
    def __init__(self, config: Configuration, saicapi: SaicApi, publisher: Publisher, vin_info: VinInfo,
                 vehicle_state: VehicleState):
        self.configuration = config
        self.saic_api = saicapi
        self.publisher = publisher
        self.vin_info = vin_info
        self.vehicle_prefix = f'{self.configuration.saic_user}/vehicles/{self.vin_info.vin}'
        self.vehicle_state = vehicle_state
        if vin_info.vin in self.configuration.abrp_token_map:
            abrp_user_token = self.configuration.abrp_token_map[vin_info.vin]
        else:
            abrp_user_token = None
        self.abrp_api = AbrpApi(self.configuration.abrp_api_key, abrp_user_token)

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
                    logging.info('Refreshing vehicle status succeeded...')
                except SaicApiException as e:
                    logging.exception('handle_vehicle loop failed during SAIC API call', exc_info=e)
                    await asyncio.sleep(float(30))
                except AbrpApiException as ae:
                    logging.exception('handle_vehicle loop failed during ABRP API call', exc_info=ae)
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
                            self.send_stop_charging_command(False)
                        case 'false':
                            self.send_stop_charging_command(True)
                        case _:
                            raise MqttGatewayException(f'Unsupported payload {msg.payload.decode()}')
                case mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE:
                    match msg.payload.decode().strip().lower():
                        case 'off':
                            logging.info('A/C will be switched off')
                            self.saic_api.stop_ac(self.vin_info)
                        case 'on':
                            logging.info('A/C will be switched on')
                            self.saic_api.start_ac(self.vin_info)
                        case 'front':
                            self.saic_api.start_ac_blowing(self.vin_info)
                        case _:
                            raise MqttGatewayException(f'Unsupported payload {msg.payload.decode()}')
                case mqtt_topics.DOORS_LOCKED:
                    match msg.payload.decode().strip().lower():
                        case 'true':
                            logging.info(f'Vehicle {self.vin_info.vin} will be locked')
                            self.saic_api.lock_vehicle(self.vin_info)
                        case 'false':
                            logging.info(f'Vehicle {self.vin_info.vin} will be unlocked')
                            self.saic_api.unlock_vehicle(self.vin_info)
                        case _:
                            raise MqttGatewayException(f'Unsupported payload {msg.payload.decode()}')
                case mqtt_topics.CLIMATE_BACK_WINDOW_HEAT:
                    match msg.payload.decode().strip().lower():
                        case 'off':
                            logging.info('Rear window heating will be switched off')
                            self.saic_api.stop_rear_window_heat(self.vin_info)
                        case 'on':
                            logging.info('Rear window heating will be switched on')
                            self.saic_api.start_rear_window_heat(self.vin_info)
                        case _:
                            raise MqttGatewayException(f'Unsupported payload {msg.payload.decode()}')
                case mqtt_topics.CLIMATE_FRONT_WINDOW_HEAT:
                    match msg.payload.decode().strip().lower():
                        case 'off':
                            logging.info('Front window heating will be switched off')
                            self.saic_api.stop_front_defrost(self.vin_info)
                        case 'on':
                            logging.info('Front window heating will be switched on')
                            self.saic_api.start_front_defrost(self.vin_info)
                        case _:
                            raise MqttGatewayException(f'Unsupported payload {msg.payload.decode()}')
                case mqtt_topics.DRIVETRAIN_SOC_TARGET:
                    payload = msg.payload.decode().strip()
                    try:
                        target_soc = int(payload)
                        match target_soc:
                            case 40:
                                target_battery_code = TargetBatteryCode.P_40
                            case 50:
                                target_battery_code = TargetBatteryCode.P_50
                            case 60:
                                target_battery_code = TargetBatteryCode.P_60
                            case 70:
                                target_battery_code = TargetBatteryCode.P_70
                            case 80:
                                target_battery_code = TargetBatteryCode.P_80
                            case 90:
                                target_battery_code = TargetBatteryCode.P_90
                            case 100:
                                target_battery_code = TargetBatteryCode.P_100
                            case _:
                                raise MqttGatewayException(f'Invalid target SoC value {target_soc}')
                        self.vehicle_state.set_target_soc(target_battery_code)
                        self.saic_api.set_target_battery_soc(target_battery_code, self.vin_info)
                    except ValueError:
                        raise MqttGatewayException(f'Error setting value for payload {payload}')
                case _:
                    # set mode, period (in)-active,...
                    self.vehicle_state.configure_by_message(topic, msg)
            self.publisher.publish_str(f'{self.vehicle_prefix}/{topic}/result', 'Success')
        except MqttGatewayException as e:
            self.publisher.publish_str(f'{self.vehicle_prefix}/{topic}/result', f'Failed: {e.message}')
            logging.exception(e.message, exc_info=e)
        except SaicApiException as se:
            self.publisher.publish_str(f'{self.vehicle_prefix}/{topic}/result', f'Failed: {se.message}')
            logging.exception(se.message, exc_info=se)

    def get_topic_without_vehicle_prefix(self, topic: str) -> str:
        global_topic_removed = topic[len(self.configuration.mqtt_topic) + 1:]
        elements = global_topic_removed.split('/')
        result = ''
        for i in range(3, len(elements) - 1):
            result += f'/{elements[i]}'
        return result[1:]

    def send_stop_charging_command(self, stop_charging: bool):
        self.saic_api.control_charging(stop_charging, self.vin_info)
        pass


class MqttGateway:
    def __init__(self, config: Configuration):
        self.configuration = config
        self.vehicle_handler = {}
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
            logging.exception('MqttGateway crashed due to SaicApiException', exc_info=e)
            raise SystemExit(e)

        for alarm_setting_type in MpAlarmSettingType:
            try:
                alarm_switches = [create_alarm_switch(alarm_setting_type)]
                self.saic_api.set_alarm_switches(alarm_switches)
                logging.info(f'Registering for {alarm_setting_type.value} messages')
            except SaicApiException:
                logging.warning(f'Failed to register for {alarm_setting_type.value} messages')

        for info in user_logging_in_response.vin_list:
            vin_info = cast(VinInfo, info)
            account_prefix = f'{self.configuration.saic_user}/{mqtt_topics.VEHICLES}/{vin_info.vin}'
            vehicle_state = VehicleState(self.publisher, account_prefix, vin_info.vin,
                                         self.get_open_wb_lp(vin_info.vin))
            vehicle_state.configure(vin_info)

            vehicle_handler = VehicleHandler(
                self.configuration,  # Gateway pointer
                self.saic_api,
                self.publisher,
                vin_info,
                vehicle_state)
            self.vehicle_handler[vin_info.vin] = vehicle_handler

        message_handler = MessageHandler(self, self.saic_api)
        asyncio.run(main(self.vehicle_handler, message_handler, self.configuration.messages_request_interval))

    def get_vehicle_handler(self, vin: str) -> VehicleHandler | None:
        if vin in self.vehicle_handler:
            return self.vehicle_handler[vin]
        else:
            logging.error(f'No vehicle handler found for VIN {vin}')
            return None

    def __on_mqtt_command_received(self, vin: str, msg: mqtt.MQTTMessage) -> None:
        vehicle_handler = self.get_vehicle_handler(vin)
        if vehicle_handler:
            vehicle_handler.handle_mqtt_command(msg)
        else:
            logging.debug(f'Command for unknown vin {vin} received')

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
                logging.info(f'{latest_vehicle_start_message.title} detected'
                             + f' at {latest_vehicle_start_message.message_time}')
                vehicle_handler = self.gateway.get_vehicle_handler(latest_vehicle_start_message.vin)
                if vehicle_handler:
                    vehicle_handler.vehicle_state.notify_message(latest_vehicle_start_message)
                # delete the vehicle start message after processing it
                try:
                    message_id = latest_vehicle_start_message.message_id
                    self.saicapi.delete_message(message_id)
                    logging.info(f'{latest_vehicle_start_message.title} message with ID {message_id} deleted')
                except SaicApiException as e:
                    logging.exception('Could not delete message from server', exc_info=e)
            elif latest_message is not None:
                vehicle_handler = self.gateway.get_vehicle_handler(latest_message.vin)
                if vehicle_handler:
                    vehicle_handler.vehicle_state.notify_message(latest_message)
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


if __name__ == '__main__':
    configuration = process_arguments()

    mqtt_gateway = MqttGateway(configuration)
    mqtt_gateway.run()
