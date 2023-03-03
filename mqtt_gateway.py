import argparse
import asyncio
import datetime
import logging
import os
import time
import urllib.parse
from typing import cast

from mqtt_publisher import MqttClient
from saicapi.publisher import Publisher
from saicapi.common_model import Configuration
from saicapi.ota_v1_1.data_model import MpUserLoggingInRsp, VinInfo, MessageListResp, Message
from saicapi.ota_v2_1.data_model import OtaRvmVehicleStatusResp25857, RvsPosition, RvsWayPoint
from saicapi.ota_v3_0.Message import MessageBodyV30
from saicapi.ota_v3_0.data_model import OtaChrgMangDataResp, RvsChargingStatus
from saicapi.ws_api import AbrpApi, SaicApi


def time_value_to_str(time_value: int) -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time_value))


async def every(__seconds: float, func, *args, **kwargs):
    while True:
        func(*args, **kwargs)
        await asyncio.sleep(__seconds)

logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)


class SaicMessage:
    def __init__(self, message_id: int, message_type: str, title: str, message_time, sender: str, content: str,
                 read_status: int, vin: str):
        self.message_id = message_id
        self.message_type = message_type
        self.title = title
        self.message_time = message_time
        self.sender = sender
        self.content = content
        self.read_status = read_status
        self.vin = vin

    def get_read_status_str(self) -> str:
        if self.read_status is None:
            return 'unknown'
        elif self.read_status == 0:
            return 'unread'
        else:
            return 'read'


def convert(message: Message) -> SaicMessage:
    if message.content is not None:
        content = message.content.decode()
    else:
        content = None
    return SaicMessage(message.message_id, message.message_type, message.title.decode(),
                       datetime.datetime.fromtimestamp(message.message_time), message.sender.decode(), content,
                       message.read_status, message.vin)


class MqttGateway:
    def __init__(self, config: Configuration):
        self.configuration = config
        self.vehicle_handler = {}
        self.publisher = MqttClient(self.configuration)
        self.saic_api = SaicApi(config, self.publisher)
        self.publisher.connect()
        
    def run(self):
        login_response_message = self.saic_api.login()
        user_logging_in_response = cast(MpUserLoggingInRsp, login_response_message.application_data)

        self.saic_api.set_alarm_switches()

        for info in user_logging_in_response.vin_list:
            vin_info = cast(VinInfo, info)
            info_prefix = f'{self.configuration.mqtt_user}/vehicles/{vin_info.vin}/info'
            self.publisher.publish_str(f'{info_prefix}/brand', vin_info.brand_name.decode())
            self.publisher.publish_str(f'{info_prefix}/model', vin_info.model_name.decode())
            self.publisher.publish_str(f'{info_prefix}/year', vin_info.model_year)
            self.publisher.publish_str(f'{info_prefix}/series', vin_info.series)
            self.publisher.publish_str(f'{info_prefix}/color', vin_info.color_name.decode())

            vehicle_handler = VehicleHandler(
                self.configuration,  # Gateway pointer
                self.saic_api,
                self.publisher,
                info)
            self.vehicle_handler[info.vin] = vehicle_handler

        message_handler = MessageHandler(self, self.saic_api)
        asyncio.run(main(self.vehicle_handler, message_handler, self.configuration.query_messages_interval * 60))

    def notify_message(self, message: SaicMessage):
        message_prefix = f'{self.configuration.mqtt_user}/vehicles/{message.vin}/info/lastMessage'
        self.publisher.publish_int(f'{message_prefix}/messageId', message.message_id)
        self.publisher.publish_str(f'{message_prefix}/messageType', message.message_type)
        self.publisher.publish_str(f'{message_prefix}/title', message.title)
        self.publisher.publish_str(f'{message_prefix}/messageTime', message.message_time.strftime("%Y-%m-%d, %H:%M:%S"))
        self.publisher.publish_str(f'{message_prefix}/sender', message.sender)
        self.publisher.publish_str(f'{message_prefix}/content', message.content)
        self.publisher.publish_str(f'{message_prefix}/status', message.get_read_status_str())
        self.publisher.publish_str(f'{message_prefix}/vin', message.vin)
        if message.vin is not None:
            handler = cast(VehicleHandler, self.vehicle_handler[message.vin])
            handler.notify_message(message)


class VehicleHandler:
    def __init__(self, config: Configuration, saicapi: SaicApi, publisher: Publisher, vin_info: VinInfo):
        self.configuration = config
        self.saic_api = saicapi
        self.publisher = publisher
        self.vin_info = vin_info
        self.last_car_activity = None
        self.force_update = True
        self.abrp_api = AbrpApi(configuration, vin_info)
        self.vehicle_prefix = f'{self.configuration.saic_user}/vehicles/{self.vin_info.vin}'

    async def handle_vehicle(self) -> None:
        self.publisher.publish_str(f'{self.vehicle_prefix}/configuration/raw',
                                   self.vin_info.model_configuration_json_str)
        configuration_prefix = f'{self.vehicle_prefix}/configuration'
        for c in self.vin_info.model_configuration_json_str.split(';'):
            property_map = {}
            for e in c.split(','):
                key_value_pair = e.split(":")
                property_map[key_value_pair[0]] = key_value_pair[1]
            self.publisher.publish_str(f'{configuration_prefix}/{property_map["code"]}', property_map["value"])
        while True:
            if (
                self.last_car_activity is None
                or self.force_update
                or self.last_car_activity < (datetime.datetime.now() - datetime.timedelta(minutes=self.configuration.query_vehicle_status_interval))
            ):
                self.force_update = False
                vehicle_status = self.update_vehicle_status()
                charge_status = self.update_charge_status()
                self.abrp_api.update_abrp(vehicle_status, charge_status)
                self.notify_car_activity(datetime.datetime.now())
                if vehicle_status.is_charging() or vehicle_status.is_engine_running():
                    self.force_update = True
                    time.sleep(60.0)
            else:
                # car not active, wait a second
                logging.debug(f'sleeping {datetime.datetime.now()}, last car activity: {self.last_car_activity}')
                time.sleep(1.0)

    def notify_car_activity(self, last_activity_time: datetime):
        if (
                self.last_car_activity is None
                or self.last_car_activity < last_activity_time
        ):
            self.last_car_activity = last_activity_time
            last_activity = self.last_car_activity.strftime("%Y-%m-%d, %H:%M:%S")
            self.publisher.publish_str(f'{self.vin_info.vin}/last_activity', last_activity)
            logging.info(f'last activity: {last_activity}')

    def notify_message(self, message: SaicMessage):
        # something happened, better check the vehicle state
        self.notify_car_activity(message.message_time)

    def update_vehicle_status(self) -> OtaRvmVehicleStatusResp25857:
        vehicle_status_rsp_msg = self.saic_api.get_vehicle_status(self.vin_info)
        while vehicle_status_rsp_msg.application_data is None:
            if vehicle_status_rsp_msg.body.error_message is not None:
                if vehicle_status_rsp_msg.body.result == 2:
                    print('you have to login again\n')
                    # TODO re-login
                # try again next time
                return cast(OtaRvmVehicleStatusResp25857, None)

            # we have received an eventId back...
            vehicle_status_rsp_msg = self.saic_api.get_vehicle_status(self.vin_info,
                                                                      vehicle_status_rsp_msg.body.event_id)

        vehicle_status_response = cast(OtaRvmVehicleStatusResp25857, vehicle_status_rsp_msg.application_data)
        basic_vehicle_status = vehicle_status_response.get_basic_vehicle_status()
        drivetrain_prefix = f'{self.vehicle_prefix}/drivetrain'
        self.publisher.publish_bool(f'{drivetrain_prefix}/running', vehicle_status_response.is_engine_running())
        self.publisher.publish_bool(f'{drivetrain_prefix}/charging', vehicle_status_response.is_charging())
        battery_voltage = basic_vehicle_status.battery_voltage / 10.0
        self.publisher.publish_float(f'{drivetrain_prefix}/auxiliaryBatteryVoltage', battery_voltage)
        mileage = basic_vehicle_status.mileage / 10.0
        self.publisher.publish_float(f'{drivetrain_prefix}/mileage', mileage)
        electric_range = basic_vehicle_status.fuel_range_elec / 10.0
        self.publisher.publish_float(f'{drivetrain_prefix}/range', electric_range)

        climate_prefix = f'{self.vehicle_prefix}/climate'
        interior_temperature = basic_vehicle_status.interior_temperature
        if interior_temperature > -128:
            self.publisher.publish_int(f'{climate_prefix}/interiorTemperature', interior_temperature)
        exterior_temperature = basic_vehicle_status.exterior_temperature
        if exterior_temperature > -128:
            self.publisher.publish_int(f'{climate_prefix}/exteriorTemperature', exterior_temperature)
        self.publisher.publish_int(f'{self.vin_info.vin}/remoteClimateState',
                                   basic_vehicle_status.remote_climate_status)
        remote_rear_window_defroster_state = basic_vehicle_status.rmt_htd_rr_wnd_st
        self.publisher.publish_int(f'{climate_prefix}/rearWindowDefrosterHeating', remote_rear_window_defroster_state)

        location_prefix = f'{self.vehicle_prefix}/location'
        gps_position = cast(RvsPosition, vehicle_status_response.gps_position)
        self.publisher.publish_json(f'{location_prefix}/position', gps_position.get_data())
        way_point = cast(RvsWayPoint, gps_position.way_point)
        speed = way_point.speed / 10.0
        self.publisher.publish_float(f'{location_prefix}/speed', speed)
        self.publisher.publish_int(f'{location_prefix}/heading', way_point.heading)

        doors_prefix = f'{self.vehicle_prefix}/doors'
        self.publisher.publish_bool(f'{doors_prefix}/driver', basic_vehicle_status.driver_window)
        self.publisher.publish_bool(f'{doors_prefix}/passenger', basic_vehicle_status.passenger_window)
        self.publisher.publish_bool(f'{doors_prefix}/rearLeft', basic_vehicle_status.rear_left_window)
        self.publisher.publish_bool(f'{doors_prefix}/rearRight', basic_vehicle_status.rear_right_window)
        self.publisher.publish_bool(f'{doors_prefix}/sunRoof', basic_vehicle_status.sun_roof_status)

        doors_prefix = f'{self.vehicle_prefix}/doors'
        self.publisher.publish_bool(f'{doors_prefix}/locked', basic_vehicle_status.lock_status)
        self.publisher.publish_bool(f'{doors_prefix}/driver', basic_vehicle_status.driver_door)
        self.publisher.publish_bool(f'{doors_prefix}/passenger', basic_vehicle_status.passenger_door)
        self.publisher.publish_bool(f'{doors_prefix}/rearLeft', basic_vehicle_status.rear_left_door)
        self.publisher.publish_bool(f'{doors_prefix}/rearRight', basic_vehicle_status.rear_right_door)
        self.publisher.publish_bool(f'{doors_prefix}/bonnet', basic_vehicle_status.bonnet_status)
        self.publisher.publish_bool(f'{doors_prefix}/boot', basic_vehicle_status.boot_status)

        tyres_prefix = f'{self.vehicle_prefix}/tyres'
        self.publisher.publish_int(f'f{tyres_prefix}/frontLeftPressure', basic_vehicle_status.front_left_tyre_pressure)
        self.publisher.publish_int(f'f{tyres_prefix}/frontRightPressure',
                                   basic_vehicle_status.front_right_tyre_pressure)
        self.publisher.publish_int(f'f{tyres_prefix}/rearLeftPressure', basic_vehicle_status.rear_left_tyre_pressure)
        self.publisher.publish_int(f'f{tyres_prefix}/rearRightPressure', basic_vehicle_status.rear_right_tyre_pressure)

        lights_prefix = f'{self.vehicle_prefix}/lights'
        self.publisher.publish_bool(f'{lights_prefix}/mainBeam', basic_vehicle_status.main_beam_status)
        self.publisher.publish_bool(f'{lights_prefix}/dippedBeam', basic_vehicle_status.dipped_beam_status)

        return vehicle_status_response

    def update_charge_status(self) -> OtaChrgMangDataResp:
        chrg_mgmt_data_rsp_msg = self.saic_api.get_charging_status(self.vin_info)
        while chrg_mgmt_data_rsp_msg.application_data is None:
            chrg_mgmt_body = cast(MessageBodyV30, chrg_mgmt_data_rsp_msg.body)
            if chrg_mgmt_body.error_message_present():
                if chrg_mgmt_body.result == 2:
                    print('you have to login again\n')
                    # TODO re-login
                # try again next time
                return cast(OtaChrgMangDataResp, None)

            chrg_mgmt_data_rsp_msg = self.saic_api.get_charging_status(self.vin_info, chrg_mgmt_body.event_id)
        charge_mgmt_data = cast(OtaChrgMangDataResp, chrg_mgmt_data_rsp_msg.application_data)
        drivetrain_prefix = f'{self.vehicle_prefix}/drivetrain'
        self.publisher.publish_float(f'{drivetrain_prefix}/current', charge_mgmt_data.get_current())
        self.publisher.publish_float(f'{drivetrain_prefix}/voltage', charge_mgmt_data.get_voltage())
        self.publisher.publish_float(f'{drivetrain_prefix}/power', charge_mgmt_data.get_power())
        self.publisher.publish_float(f'{drivetrain_prefix}/soc', charge_mgmt_data.bmsPackSOCDsp / 10.0)
        charge_status = cast(RvsChargingStatus, charge_mgmt_data.chargeStatus)
        self.publisher.publish_int(f'{drivetrain_prefix}/chargingType', charge_status.charging_type)
        self.publisher.publish_bool(f'{drivetrain_prefix}/chargerConnected', charge_status.charging_gun_state)

        self.publisher.publish_int(f'{self.vin_info.vin}/bms/bmsChrgCtrlDspCmd', charge_mgmt_data.bmsChrgCtrlDspCmd)
        self.publisher.publish_int(f'{self.vin_info.vin}/bms/bmsChrgOtptCrntReq',
                                   charge_mgmt_data.bmsChrgOtptCrntReq)
        self.publisher.publish_int(f'{self.vin_info.vin}/bms/bmsChrgSts', charge_mgmt_data.bmsChrgSts)
        self.publisher.publish_int(f'{self.vin_info.vin}/bms/bmsPackVol', charge_mgmt_data.bmsPackVol)
        self.publisher.publish_int(f'{self.vin_info.vin}/bms/bmsPTCHeatReqDspCmd',
                                   charge_mgmt_data.bmsPTCHeatReqDspCmd)
        return charge_mgmt_data


class MessageHandler:
    def __init__(self, gateway: MqttGateway, saicapi: SaicApi):
        self.gateway = gateway
        self.saicapi = saicapi

    def polling(self):
        message_list_rsp_msg = self.saicapi.get_message_list()

        if message_list_rsp_msg.application_data is not None:
            message_list_rsp = cast(MessageListResp, message_list_rsp_msg.application_data)
            for message in message_list_rsp.messages:
                self.gateway.notify_message(convert(message))


async def main(vh_map: dict, message_handler: MessageHandler, query_messages_interval: int):
    tasks = []
    for key in vh_map:
        print(f'{key}')
        vh = cast(VehicleHandler, vh_map[key])
        task = asyncio.create_task(vh.handle_vehicle())
        tasks.append(task)

    tasks.append(asyncio.create_task(every(float(query_messages_interval), message_handler.polling())))

    for task in tasks:
        # make sure we wait on all futures before exiting
        await task


def process_arguments() -> Configuration:
    config = Configuration()
    parser = argparse.ArgumentParser(prog='MQTT Gateway')
    try:
        parser.add_argument('-m', '--mqtt-uri', help='The URI to the MQTT Server. Environment Variable: MQTT_URI,'
                                                     + 'TCP: tcp://mqtt.eclipseprojects.io:1883 '
                                                     + 'WebSocket: ws://mqtt.eclipseprojects.io:9001',
                            default=os.getenv('MQTT_URI'), dest='mqtt_uri', required=True)
        parser.add_argument('--mqtt-user', help='The MQTT user name. Environment Variable: MQTT_USER',
                            default=os.getenv('MQTT_USER'), dest='mqtt_user', required=False)
        parser.add_argument('--mqtt-password', help='The MQTT password. Environment Variable: MQTT_PASSWORD',
                            default=os.getenv('MQTT_PASSWORD'), dest='mqtt_password', required=False)
        parser.add_argument('--mqtt-topic-prefix', help='MQTT topic prefix. Environment Variable: MQTT_TOPIC'
                                                        + 'Default is saic',
                            default=os.getenv('MQTT_TOPIC', 'saic'), dest='mqtt_topic', required=False)
        parser.add_argument('-s', '--saic-uri', help='The SAIC uri. Environment Variable: SAIC_URI Default is the'
                                                     + ' European Production Endpoint: https://tap-eu.soimt.com',
                            default=os.getenv('SAIC_URI', 'https://tap-eu.soimt.com'), dest='saic_uri', required=False)
        parser.add_argument('-u', '--saic-user',
                            help='The SAIC user name. Environment Variable: SAIC_USER', default=os.getenv('SAIC_USER'),
                            dest='saic_user', required=True)
        parser.add_argument('-p', '--saic-password', help='The SAIC password. Environment Variable: SAIC_PASSWORD',
                            default=os.getenv('SAIC_PASSWORD'), dest='saic_password', required=True)
        parser.add_argument('--abrp-api-key', help='The API key for the A Better Route Planer telemetry API.'
                                                   + ' Default is the open source telemetry'
                                                   + ' API key 8cfc314b-03cd-4efe-ab7d-4431cd8f2e2d.'
                                                   + ' Environment Variable: ABRP_API_KEY',
                            default=os.getenv('ABRP_API_KEY', '8cfc314b-03cd-4efe-ab7d-4431cd8f2e2d'),
                            dest='abrp_api_key', required=False)
        parser.add_argument('--abrp-user-token', help='The mapping of VIN to ABRP User Token.'
                                                      + ' Multiple mappings can be provided seperated by ,'
                                                      + ' Example: LSJXXXX=12345-abcdef,LSJYYYY=67890-ghijkl,'
                                                      + ' Environment Variable: ABRP_USER_TOKEN',
                            default=os.getenv('ABRP_USER_TOKEN'), dest='abrp_user_token', required=False)
        args = parser.parse_args()
        config.mqtt_user = args.mqtt_user
        config.mqtt_password = args.mqtt_password
        config.mqtt_topic = args.mqtt_topic
        config.saic_uri = args.saic_uri
        config.saic_user = args.saic_user
        config.saic_password = args.saic_password
        config.abrp_api_key = args.abrp_api_key
        if args.abrp_user_token:
            map_entries = args.abrp_user_token.split(',')
            for entry in map_entries:
                key_value_pair = entry.split('=')
                key = key_value_pair[0]
                value = key_value_pair[1]
                config.abrp_token_map[key] = value
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


configuration = process_arguments()

mqtt_gateway = MqttGateway(configuration)
mqtt_gateway.run()
