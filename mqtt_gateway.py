import argparse
import asyncio
import datetime
import os
import time
from typing import cast

from mqtt_publisher import MqttClient
from saicapi.publisher import Publisher
from saicapi.common_model import Configuration
from saicapi.ota_v1_1.data_model import MpUserLoggingInRsp, VinInfo, MessageListResp, Message
from saicapi.ota_v2_1.data_model import OtaRvmVehicleStatusResp25857, RvsPosition
from saicapi.ota_v3_0.Message import MessageBodyV30
from saicapi.ota_v3_0.data_model import OtaChrgMangDataResp, RvsChargingStatus
from saicapi.ws_api import AbrpApi, SaicApi


def time_value_to_str(time_value: int) -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time_value))


async def every(__seconds: float, func, *args, **kwargs):
    while True:
        func(*args, **kwargs)
        await asyncio.sleep(__seconds)


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

    def get_data(self) -> dict:
        return {
            'messageId': self.message_id,
            'messageType': self.message_type,
            'title': self.title,
            'messageTime': self.message_time,
            'sender': self.sender,
            'content': self.content,
            'readStatus': self.read_status,
            'vin': self.vin
        }


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
        uid = login_response_message.body.uid
        user_logging_in_response = cast(MpUserLoggingInRsp, login_response_message.application_data)
        token = user_logging_in_response.token

        self.saic_api.set_alarm_switches(uid, token)

        for info in user_logging_in_response.vin_list:
            vehicle_handler = VehicleHandler(
                self.configuration,  # Gateway pointer
                self.saic_api,
                self.publisher,
                uid,
                token,
                info)
            self.vehicle_handler[info.vin] = vehicle_handler

        message_handler = MessageHandler(self, self.saic_api, self.configuration.saic_uri,
                                         login_response_message.body.uid, login_response_message.body.token)
        asyncio.run(main(self.vehicle_handler, message_handler, self.configuration.query_messages_interval * 60))

    def notify_message(self, message: SaicMessage):
        self.publisher.publish_json(f'{message.message_id}', message.get_data())
        if message.vin is not None:
            handler = cast(VehicleHandler, self.vehicle_handler[message.vin])
            handler.notify_message(message)


class VehicleHandler:
    def __init__(self, config: Configuration, saicapi: SaicApi, publisher: Publisher, uid: str, token: str,
                 vin_info: VinInfo):
        self.configuration = config
        self.saic_api = saicapi
        self.publisher = publisher
        self.uid = uid
        self.token = token
        self.vin_info = vin_info
        self.last_car_activity = None
        self.force_last_activity_update = True
        self.abrp_api = AbrpApi(configuration, vin_info)

    async def handle_vehicle(self) -> None:
        self.publisher.publish_str(f'{self.vin_info.vin}/configuration/raw', self.vin_info.model_configuration_json_str)
        for c in self.vin_info.model_configuration_json_str.split(';'):
            property_map = {}
            for e in c.split(','):
                key_value_pair = e.split(":")
                property_map[key_value_pair[0]] = key_value_pair[1]
            self.publisher.publish_str(f'{self.vin_info.vin}/configuration/{property_map["code"]}', property_map["value"])
        while True:
            if (
                self.last_car_activity is None
                or self.force_last_activity_update
                or self.last_car_activity < (datetime.datetime.now() - datetime.timedelta(minutes=self.configuration.query_vehicle_status_interval))
            ):
                self.force_last_activity_update = False
                vehicle_status = self.update_vehicle_status()
                charge_status = self.update_charge_status()
                self.abrp_api.update_abrp(vehicle_status, charge_status)
                self.notify_car_activity(datetime.datetime.now())
            else:
                # car not active, wait a second
                print(f'sleeping {datetime.datetime.now()}, last car activity: {self.last_car_activity}')
                time.sleep(float(1))

    def notify_car_activity(self, last_activity_time: datetime):
        if (
                self.last_car_activity is None
                or self.last_car_activity < last_activity_time
        ):
            self.last_car_activity = last_activity_time
            self.publisher.publish_str(f'{self.vin_info.vin}/last_activity',
                                       self.last_car_activity.strftime("%Y-%m-%d, %H:%M:%S"))

    def notify_message(self, message: SaicMessage):
        self.publisher.publish_json(f'{self.vin_info.vin}/message', message.get_data())
        # something happened, better check the vehicle state
        self.notify_car_activity(message.message_time)

    def update_vehicle_status(self) -> OtaRvmVehicleStatusResp25857:
        vehicle_status_rsp_msg = self.saic_api.get_vehicle_status(self.uid, self.token, self.vin_info)
        while vehicle_status_rsp_msg.application_data is None:
            if vehicle_status_rsp_msg.body.error_message is not None:
                if vehicle_status_rsp_msg.body.result == 2:
                    print('you have to login again\n')
                    # TODO re-login
                # try again next time
                return cast(OtaRvmVehicleStatusResp25857, None)

            # we have received an eventId back...
            vehicle_status_rsp_msg = self.saic_api.get_vehicle_status(self.uid, self.token, self.vin_info,
                                                                      vehicle_status_rsp_msg.body.event_id)

        vehicle_status_response = cast(OtaRvmVehicleStatusResp25857, vehicle_status_rsp_msg.application_data)
        basic_vehicle_status = vehicle_status_response.get_basic_vehicle_status()
        engine_running = vehicle_status_response.is_engine_running()
        is_charging = vehicle_status_response.is_charging()
        if is_charging or engine_running:
            self.force_last_activity_update = True

        self.publisher.publish_bool(f'{self.vin_info.vin}/running', engine_running)
        self.publisher.publish_bool(f'{self.vin_info.vin}/charging', is_charging)

        interior_temperature = basic_vehicle_status.interior_temperature
        if interior_temperature > -128:
            self.publisher.publish_int(f'{self.vin_info.vin}/temperature/interior', interior_temperature)
        exterior_temperature = basic_vehicle_status.exterior_temperature
        if exterior_temperature > -128:
            self.publisher.publish_int(f'{self.vin_info.vin}/temperature/exterior', exterior_temperature)
        battery_voltage = basic_vehicle_status.battery_voltage / 10.0
        self.publisher.publish_float(f'{self.vin_info.vin}/auxillary_battery', battery_voltage)
        gps_position = cast(RvsPosition, vehicle_status_response.gps_position)
        self.publisher.publish_json(f'{self.vin_info.vin}/gps/json', gps_position.get_data())
        speed = gps_position.way_point.speed / 10.0
        self.publisher.publish_float(f'{self.vin_info.vin}/speed', speed)
        lock_status = basic_vehicle_status.lock_status
        self.publisher.publish_bool(f'{self.vin_info.vin}/locked', lock_status)
        remote_climate = basic_vehicle_status.remote_climate_status
        self.publisher.publish_int(f'{self.vin_info.vin}/remoteClimate', remote_climate)
        remote_rear_window_heater = basic_vehicle_status.rmt_htd_rr_wnd_st
        self.publisher.publish_int(f'{self.vin_info.vin}/remoteRearWindowHeater', remote_rear_window_heater)
        mileage = basic_vehicle_status.mileage / 10.0
        self.publisher.publish_float(f'{self.vin_info.vin}/milage', mileage)
        electric_range = basic_vehicle_status.fuel_range_elec / 10.0
        self.publisher.publish_float(f'{self.vin_info.vin}/range/electric', electric_range)
        return vehicle_status_response

    def update_charge_status(self) -> OtaChrgMangDataResp:
        chrg_mgmt_data_rsp_msg = self.saic_api.get_charging_status(self.uid, self.token, self.vin_info)
        while chrg_mgmt_data_rsp_msg.application_data is None:
            chrg_mgmt_body = cast(MessageBodyV30, chrg_mgmt_data_rsp_msg.body)
            if chrg_mgmt_body.error_message_present():
                if chrg_mgmt_body.result == 2:
                    print('you have to login again\n')
                    # TODO re-login
                # try again next time
                return cast(OtaChrgMangDataResp, None)

            chrg_mgmt_data_rsp_msg = self.saic_api.get_charging_status(self.uid, self.token, self.vin_info,
                                                                       chrg_mgmt_body.event_id)
        charge_mgmt_data = cast(OtaChrgMangDataResp, chrg_mgmt_data_rsp_msg.application_data)
        self.publisher.publish_str(f'{self.vin_info.vin}/current', str(charge_mgmt_data.get_current()))
        self.publisher.publish_str(f'{self.vin_info.vin}/voltage', str(charge_mgmt_data.get_voltage()))
        self.publisher.publish_str(f'{self.vin_info.vin}/power', str(charge_mgmt_data.get_power()))
        charge_status = cast(RvsChargingStatus, charge_mgmt_data.chargeStatus)
        self.publisher.publish_int(f'{self.vin_info.vin}/charge/type', charge_status.charging_type)
        self.publisher.publish_int(f'{self.vin_info.vin}/bms/bmsChrgCtrlDspCmd', charge_mgmt_data.bmsChrgCtrlDspCmd)
        self.publisher.publish_int(f'{self.vin_info.vin}/bms/bmsChrgOtptCrntReq',
                                   charge_mgmt_data.bmsChrgOtptCrntReq)
        self.publisher.publish_int(f'{self.vin_info.vin}/bms/bmsChrgSts', charge_mgmt_data.bmsChrgSts)
        self.publisher.publish_int(f'{self.vin_info.vin}/bms/bmsPackCrnt', charge_mgmt_data.bmsPackCrnt)
        self.publisher.publish_int(f'{self.vin_info.vin}/bms/bmsPackVol', charge_mgmt_data.bmsPackVol)
        self.publisher.publish_int(f'{self.vin_info.vin}/bms/bmsPTCHeatReqDspCmd',
                                   charge_mgmt_data.bmsPTCHeatReqDspCmd)
        self.publisher.publish_str(f'{self.vin_info.vin}/soc', str(charge_mgmt_data.bmsPackSOCDsp / 10.0))
        return charge_mgmt_data


class MessageHandler:
    def __init__(self, gateway: MqttGateway, saicapi: SaicApi, saic_url: str, uid: str, token: str):
        self.gateway = gateway
        self.saicapi = saicapi
        self.saic_url = saic_url
        self.uid = uid
        self.token = token

    def polling(self):
        message_list_rsp_msg = self.saicapi.get_message_list(self.uid, self.token)

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
        config.mqtt_uri = args.mqtt_uri
        config.mqtt_user = args.mqtt_user
        config.mqtt_password = args.mqtt_password
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
        return config
    except argparse.ArgumentError as err:
        parser.print_help()
        SystemExit(err)


configuration = process_arguments()

mqtt_gateway = MqttGateway(configuration)
mqtt_gateway.run()
