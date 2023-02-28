import hashlib
import urllib.parse
from typing import cast

import requests as requests

from saicapi.publisher import Publisher
from saicapi.common_model import Configuration, MessageV2, MessageBodyV2, Header
from saicapi.ota_v1_1.Message import MessageCoderV11
from saicapi.ota_v1_1.data_model import VinInfo, MpUserLoggingInReq, MpUserLoggingInRsp, AlarmSwitchReq, \
    MpAlarmSettingType, AlarmSwitch, MessageBodyV11, MessageV11, MessageListReq, StartEndNumber, MessageListResp
from saicapi.ota_v2_1.Message import MessageCoderV21
from saicapi.ota_v2_1.data_model import OtaRvmVehicleStatusReq, OtaRvmVehicleStatusResp25857
from saicapi.ota_v3_0.Message import MessageCoderV30, MessageV30, MessageBodyV30
from saicapi.ota_v3_0.data_model import OtaChrgMangDataResp

UID_INIT = '0000000000000000000000000000000000000000000000000#'


class AbrpApi:
    def __init__(self, configuration: Configuration, vin_info: VinInfo) -> None:
        self.configuration = configuration
        self.vin_info = vin_info

    def update_abrp(self, vehicle_status: OtaRvmVehicleStatusResp25857, charge_status: OtaChrgMangDataResp):
        # TODO create MQTT message
        abrp_user_token = self.configuration.abrp_token_map.get(self.vin_info.vin)
        if (
                self.configuration.abrp_api_key is not None
                and abrp_user_token is not None
                and vehicle_status is not None
                and charge_status is not None
        ):
            # Request
            tlm_send_url = 'https://api.iternio.com/1/tlm/send'
            data = {
                'utc': vehicle_status.get_gps_position().timestamp_4_short.seconds,
                'soc': (charge_status.bmsPackSOCDsp / 10.0),
                'power': charge_status.get_power(),
                'speed': (vehicle_status.get_gps_position().get_way_point().speed / 10.0),
                'lat': (vehicle_status.get_gps_position().get_way_point().get_position().latitude / 1000000.0),
                'lon': (vehicle_status.get_gps_position().get_way_point().get_position().longitude / 1000000.0),
                'is_charging': vehicle_status.is_charging(),
                'is_parked': vehicle_status.is_parked(),
                'heading': vehicle_status.get_gps_position().get_way_point().heading,
                'elevation': vehicle_status.get_gps_position().get_way_point().get_position().altitude,
                'voltage': charge_status.get_voltage(),
                'current': charge_status.get_current()
            }
            exterior_temperature = vehicle_status.get_basic_vehicle_status().exterior_temperature
            if exterior_temperature != -128:
                data['ext_temp'] = exterior_temperature
            mileage = vehicle_status.get_basic_vehicle_status().mileage
            if mileage > 0:
                data['odometer'] = mileage / 10.0
            range_elec = vehicle_status.get_basic_vehicle_status().fuel_range_elec
            if range_elec > 0:
                data['est_battery_range'] = range_elec / 10.0

            try:
                tlm_response = requests.get(tlm_send_url, params={
                    'api_key': self.configuration.abrp_api_key,
                    'token': abrp_user_token,
                    'tlm': urllib.parse.urlencode(data)
                })
                tlm_response.raise_for_status()
                print(f'ABRP: {tlm_response.content}')
            except requests.exceptions.RequestException as e:
                raise SystemExit(e)


class SaicApi:
    def __init__(self, configuration: Configuration, publisher: Publisher):
        self.configuration = configuration
        self.publisher = publisher
        self.message_v1_1_coder = MessageCoderV11()
        self.message_V2_1_coder = MessageCoderV21()
        self.message_V3_0_coder = MessageCoderV30()
        self.cookies = None

    def login(self) -> MessageV11:
        application_data = MpUserLoggingInReq()
        application_data.password = self.configuration.saic_password
        header = Header()
        header.protocol_version = 17
        login_request_message = MessageV11(header, MessageBodyV11(), application_data)
        application_id = '501'
        application_data_protocol_version = 513
        self.message_v1_1_coder.initialize_message(
            UID_INIT[len(self.configuration.saic_user):] + self.configuration.saic_user,
            cast(str, None),
            application_id,
            application_data_protocol_version,
            1,
            login_request_message)
        self.publish_json_value(application_id, application_data_protocol_version, login_request_message.get_data())
        login_request_hex = self.message_v1_1_coder.encode_request(login_request_message)
        self.publish_raw_value(application_id, application_data_protocol_version, login_request_hex)
        login_response_hex = self.send_request(login_request_hex,
                                               urllib.parse.urljoin(self.configuration.saic_uri, '/TAP.Web/ota.mp'))
        self.publish_raw_value(application_id, application_data_protocol_version, login_response_hex)
        login_response_message = MessageV11(header, MessageBodyV11(), MpUserLoggingInRsp())
        self.message_v1_1_coder.decode_response(login_response_hex, login_response_message)
        self.publish_json_value(application_id, application_data_protocol_version, login_response_message.get_data())
        if login_response_message.body.error_message is not None:
            raise SystemExit(login_response_message.body.error_message.decode())
        return login_response_message

    def set_alarm_switches(self, uid: str, token: str) -> None:
        alarm_switch_req = AlarmSwitchReq()
        for setting_type in MpAlarmSettingType:
            alarm_switch_req.alarm_switch_list.append(create_alarm_switch(setting_type))
        alarm_switch_req.pin = hash_md5('123456')

        header = Header()
        header.protocol_version = 17
        alarm_switch_req_message = MessageV11(header, MessageBodyV11(), alarm_switch_req)
        application_id = '521'
        application_data_protocol_version = 513
        self.message_v1_1_coder.initialize_message(
            uid,
            token,
            application_id,
            application_data_protocol_version,
            1,
            alarm_switch_req_message)
        self.publish_json_value(application_id, application_data_protocol_version, alarm_switch_req_message.get_data())
        alarm_switch_request_hex = self.message_v1_1_coder.encode_request(alarm_switch_req_message)
        self.publish_raw_value(application_id, application_data_protocol_version, alarm_switch_request_hex)
        alarm_switch_response_hex = self.send_request(alarm_switch_request_hex,
                                                      urllib.parse.urljoin(self.configuration.saic_uri,
                                                                           '/TAP.Web/ota.mp'))
        self.publish_raw_value(application_id, application_data_protocol_version, alarm_switch_response_hex)
        alarm_switch_response_message = MessageV11(header, MessageBodyV11())
        self.message_v1_1_coder.decode_response(alarm_switch_response_hex, alarm_switch_response_message)
        self.publish_json_value(application_id, application_data_protocol_version,
                                alarm_switch_response_message.get_data())

        if alarm_switch_response_message.body.error_message is not None:
            raise ValueError(alarm_switch_response_message.body.error_message.decode())

    def get_vehicle_status(self, uid: str, token: str, vin_info: VinInfo,
                           event_id: str = None) -> MessageV2:
        vehicle_status_req = OtaRvmVehicleStatusReq()
        vehicle_status_req.veh_status_req_type = 2
        vehicle_status_req_msg = MessageV2(MessageBodyV2(), vehicle_status_req)
        application_id = '511'
        application_data_protocol_version = 25857
        self.message_V2_1_coder.initialize_message(uid, token, vin_info.vin, "511", 25857, 1, vehicle_status_req_msg)
        if event_id is not None:
            vehicle_status_req_msg.body.event_id = event_id
        self.publish_json_value(application_id, application_data_protocol_version, vehicle_status_req_msg.get_data())
        vehicle_status_req_hex = self.message_V2_1_coder.encode_request(vehicle_status_req_msg)
        self.publish_raw_value(application_id, application_data_protocol_version, vehicle_status_req_hex)
        vehicle_status_rsp_hex = self.send_request(vehicle_status_req_hex,
                                                   urllib.parse.urljoin(self.configuration.saic_uri,
                                                                        '/TAP.Web/ota.mpv21'))
        self.publish_raw_value(application_id, application_data_protocol_version, vehicle_status_rsp_hex)
        vehicle_status_rsp_msg = MessageV2(MessageBodyV2(), OtaRvmVehicleStatusResp25857())
        self.message_V2_1_coder.decode_response(vehicle_status_rsp_hex, vehicle_status_rsp_msg)
        app_data = cast(OtaRvmVehicleStatusResp25857, vehicle_status_rsp_msg.application_data)
        if(
                app_data.status_time is None
                and app_data.basic_vehicle_status is None
                and app_data.gps_position is None
        ):
            vehicle_status_rsp_msg.application_data = None
        self.publish_json_value(application_id, application_data_protocol_version, vehicle_status_rsp_msg.get_data())
        return vehicle_status_rsp_msg

    def get_charging_status(self, uid: str, token: str, vin_info: VinInfo, event_id: str = None) -> MessageV30:
        chrg_mgmt_data_req_msg = MessageV30(MessageBodyV30())
        application_id = '516'
        application_data_protocol_version = 768
        self.message_V3_0_coder.initialize_message(uid, token, vin_info.vin, '516', 768, 5, chrg_mgmt_data_req_msg)
        if event_id is not None:
            chrg_mgmt_data_req_msg.body.event_id = event_id
        self.publish_json_value(application_id, application_data_protocol_version, chrg_mgmt_data_req_msg.get_data())
        chrg_mgmt_data_req_hex = self.message_V3_0_coder.encode_request(chrg_mgmt_data_req_msg)
        self.publish_raw_value(application_id, application_data_protocol_version, chrg_mgmt_data_req_hex)
        chrg_mgmt_data_rsp_hex = self.send_request(chrg_mgmt_data_req_hex,
                                                   urllib.parse.urljoin(self.configuration.saic_uri,
                                                                        '/TAP.Web/ota.mpv30'))
        self.publish_raw_value(application_id, application_data_protocol_version, chrg_mgmt_data_rsp_hex)
        chrg_mgmt_data_rsp_msg = MessageV30(MessageBodyV30(), OtaChrgMangDataResp())
        self.message_V3_0_coder.decode_response(chrg_mgmt_data_rsp_hex, chrg_mgmt_data_rsp_msg)
        self.publish_json_value(application_id, application_data_protocol_version, chrg_mgmt_data_rsp_msg.get_data())
        return chrg_mgmt_data_rsp_msg

    def get_message_list(self, uid: str, token: str) -> MessageV11:
        message_list_request = MessageListReq()
        message_list_request.start_end_number = StartEndNumber()
        message_list_request.start_end_number.start_number = 1
        message_list_request.start_end_number.end_number = 5
        message_list_request.message_group = 'ALARM'

        header = Header()
        header.protocol_version = 18
        message_body = MessageBodyV11()
        message_list_req_msg = MessageV11(header, message_body, message_list_request)
        application_id = '513'
        application_data_protocol_version = 513
        self.message_v1_1_coder.initialize_message(uid, token, '513', 513, 1, message_list_req_msg)
        self.publish_json_value(application_id, application_data_protocol_version, message_list_req_msg.get_data())
        message_list_req_hex = self.message_v1_1_coder.encode_request(message_list_req_msg)
        self.publish_raw_value(application_id, application_data_protocol_version, message_list_req_hex)
        message_list_rsp_hex = self.send_request(message_list_req_hex,
                                                 urllib.parse.urljoin(self.configuration.saic_uri, '/TAP.Web/ota.mp'))
        self.publish_raw_value(application_id, application_data_protocol_version, message_list_rsp_hex)
        message_list_rsp_msg = MessageV11(header, MessageBodyV11(), MessageListResp())
        self.message_v1_1_coder.decode_response(message_list_rsp_hex, message_list_rsp_msg)
        self.publish_json_value(application_id, application_data_protocol_version, message_list_rsp_msg.get_data())
        return message_list_rsp_msg

    def publish_raw_value(self, application_id: str, application_data_protocol_version: int, raw: str):
        self.publisher.publish_str(f'{application_id}_{application_data_protocol_version}/raw', raw)

    def publish_json_value(self, application_id: str, application_data_protocol_version: int, data: dict):
        self.publisher.publish_json(f'{application_id}_{application_data_protocol_version}/json', data)

    def send_request(self, hex_message: str, endpoint) -> str:
        headers = {
            'Accept': '*/*',
            'Content-Type': 'text/html',
            'Accept-Encoding': 'gzip, deflate, br',
            'User-Agent': 'MG iSMART/1.1.1 (iPhone; iOS 16.3; Scale/3.00)',
            'Accept-Language': 'de-DE;q=1, en-DE;q=0.9, lu-DE;q=0.8, fr-DE;q=0.7',
            'Content-Length': str(len(hex_message))
        }

        try:
            response = requests.post(url=endpoint, data=hex_message, headers=headers, cookies=self.cookies)
            response.raise_for_status()
            self.cookies = response.cookies
            return response.content.decode()
        except requests.exceptions.RequestException as e:
            raise SystemExit(e)


def hash_md5(password: str) -> str:
    return hashlib.md5(password.encode('utf-8')).hexdigest()


def create_alarm_switch(alarm_setting_type: MpAlarmSettingType) -> AlarmSwitch:
    alarm_switch = AlarmSwitch()
    alarm_switch.alarm_setting_type = alarm_setting_type.value
    alarm_switch.alarm_switch = True
    alarm_switch.function_switch = True
    return alarm_switch
