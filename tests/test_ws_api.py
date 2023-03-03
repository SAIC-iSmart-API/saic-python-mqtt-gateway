from typing import cast
from unittest import TestCase
from unittest.mock import patch, PropertyMock

import requests

from log_publisher import Logger
from saicapi.common_model import Configuration, Header, MessageV2, MessageBodyV2
from saicapi.ota_v1_1.Message import MessageCoderV11
from saicapi.ota_v1_1.data_model import MessageV11, MpUserLoggingInRsp, MessageBodyV11, VinInfo
from saicapi.ota_v2_1.Message import MessageCoderV21
from saicapi.ota_v2_1.data_model import OtaRvmVehicleStatusResp25857, RvsPosition, RvsWayPoint, RvsWgs84Point, \
    Timestamp4Short, RvsBasicStatus25857
from saicapi.ota_v3_0.Message import MessageBodyV30, MessageV30, MessageCoderV30
from saicapi.ota_v3_0.data_model import OtaChrgMangDataResp, RvsChargingStatus
from saicapi.ws_api import SaicApi

TOKEN = '99X9999X-90XX-99X9-99X9-9XX9XX0X9X9XXX9X'
UID = '00000000000000000000000000000000000090000000099999'
VIN = 'vin10000000000000'


def mock_login_response_hex(message_coder: MessageCoderV11) -> str:
    app_data = MpUserLoggingInRsp()
    app_data.user_name = 'user_name'
    app_data.vin_list.append(create_vin_info(VIN))
    app_data.vin_list.append(create_vin_info('vin20000000000000'))
    app_data.vin_list.append(create_vin_info('vin30000000000000'))
    header = Header()
    header.protocol_version = 17
    login_rsp_message = MessageV11(header, MessageBodyV11(), app_data)
    message_coder.initialize_message(
        UID,
        TOKEN,
        '501',
        513,
        1,
        login_rsp_message)
    return message_coder.encode_request(login_rsp_message)


def create_vin_info(vin: str) -> VinInfo:
    vin_info = VinInfo()
    vin_info.vin = vin
    vin_info.series = 'series'
    vin_info.brand_name = b'brandName'
    vin_info.model_name = b'modelName'
    vin_info.active = True
    vin_info.model_configuration_json_str = 'name:Tire pressure monitoring system,code:J17,value:1;'\
                                            + 'name:Regular airbags,code:Q00,value:1;'\
                                            + 'name:Front-seat airbags,code:Q01,value:1;'\
                                            + 'name:Airbag switch,code:Q09,value:1;'\
                                            + 'name:Sun Roof,code:S35,value:0;'\
                                            + 'name:Remote control,code:S61,value:1;'\
                                            + 'name:Air conditioning,code:T11,value:1;'\
                                            + 'name:Electric Power Steering,code:EPS,value:1;'\
                                            + 'name:Security alert,code:SA64,value:0111110000000000001000000100101000000010100000000000000000000110;'\
                                            + 'name:Bonnut Status,code:BONNUT,value:1;'\
                                            + 'name:Door Status,code:DOOR,value:1111;'\
                                            + 'name:Boot Status,code:BOOT,value:1;'\
                                            + 'name:Engine Status,code:ENGINE,value:1;'\
                                            + 'name:Electric Vehicle,code:EV,value:0;'\
                                            + 'name:HeatedSeat,code:HeatedSeat,value:0;'\
                                            + 'name:Key Position,code:KEYPOS,value:1;'\
                                            + 'name:Energy state,code:ENERGY,value:0;'\
                                            + 'name:Battery Voltage,code:BATTERY,value:1;'\
                                            + 'name:Interior Temperature,code:INTEMP,value:1;'\
                                            + 'name:Exterior Temperature,code:EXTEMP,value:1;'\
                                            + 'name:Window Status,code:WINDOW,value:0000;'\
                                            + 'name:Left-Right Driving,code:LRD,value:0;'\
                                            + 'name:Bluetooth Key,code:BTKEY,value:0;'\
                                            + 'name:Battery Type,code:BType,value:2'
    return vin_info


def mock_alarm_switch_response_hex(message_coder: MessageCoderV11) -> str:
    header = Header()
    header.protocol_version = 17
    alarm_switch_rsp_message = MessageV11(header, MessageBodyV11())
    message_coder.initialize_message(
        UID,
        TOKEN,
        '521',
        513,
        1,
        alarm_switch_rsp_message)
    return message_coder.encode_request(alarm_switch_rsp_message)


def mock_vehicle_status_response(message_v2_1_coder: MessageCoderV21, uid: str, token: str, vin_info: VinInfo) -> str:
    vehicle_status_response = OtaRvmVehicleStatusResp25857()
    vehicle_status_response.status_time = 1000000000
    vehicle_status_response.gps_position = RvsPosition()
    vehicle_status_response.gps_position.way_point = RvsWayPoint()
    vehicle_status_response.gps_position.way_point.position = RvsWgs84Point()
    vehicle_status_response.gps_position.way_point.position.latitude = 10000000
    vehicle_status_response.gps_position.way_point.position.longitude = 10000000
    vehicle_status_response.gps_position.way_point.position.altitude = 100
    vehicle_status_response.gps_position.way_point.heading = 90
    vehicle_status_response.gps_position.way_point.speed = 100
    vehicle_status_response.gps_position.way_point.hdop = 10
    vehicle_status_response.gps_position.way_point.satellites = 3
    vehicle_status_response.gps_position.timestamp_4_short = Timestamp4Short()
    vehicle_status_response.gps_position.timestamp_4_short.seconds = 1000000000
    vehicle_status_response.gps_position.gps_status = 'fix3D'
    vehicle_status_response.basic_vehicle_status = RvsBasicStatus25857()
    vehicle_status_response.basic_vehicle_status.driver_door = False
    vehicle_status_response.basic_vehicle_status.passenger_door = False
    vehicle_status_response.basic_vehicle_status.rear_left_door = False
    vehicle_status_response.basic_vehicle_status.rear_right_Door = False
    vehicle_status_response.basic_vehicle_status.boot_status = True
    vehicle_status_response.basic_vehicle_status.bonnet_status = False
    vehicle_status_response.basic_vehicle_status.lock_status = True
    vehicle_status_response.basic_vehicle_status.side_light_status = False
    vehicle_status_response.basic_vehicle_status.dipped_beam_status = False
    vehicle_status_response.basic_vehicle_status.main_beam_status = False
    vehicle_status_response.basic_vehicle_status.power_mode = 1
    vehicle_status_response.basic_vehicle_status.last_key_seen = 32000
    vehicle_status_response.basic_vehicle_status.current_journey_distance = 7
    vehicle_status_response.basic_vehicle_status.current_journey_id = 42
    vehicle_status_response.basic_vehicle_status.interior_temperature = 22
    vehicle_status_response.basic_vehicle_status.exterior_temperature = 10
    vehicle_status_response.basic_vehicle_status.fuel_level_prc = 125
    vehicle_status_response.basic_vehicle_status.fuel_range = 32000
    vehicle_status_response.basic_vehicle_status.remote_climate_status = 7
    vehicle_status_response.basic_vehicle_status.can_bus_active = False
    vehicle_status_response.basic_vehicle_status.time_of_last_canbus_activity = 1000000000
    vehicle_status_response.basic_vehicle_status.clstr_dspd_fuel_lvl_sgmt = 125
    vehicle_status_response.basic_vehicle_status.mileage = 1000
    vehicle_status_response.basic_vehicle_status.battery_voltage = 32000
    vehicle_status_response.basic_vehicle_status.hand_brake = True
    vehicle_status_response.basic_vehicle_status.veh_elec_rng_dsp = 125
    vehicle_status_response.basic_vehicle_status.rmt_htd_rr_wnd_st = 125
    vehicle_status_response.basic_vehicle_status.engine_status = 0
    vehicle_status_response.basic_vehicle_status.extended_data2 = 0  # is charging
    vehicle_status_response.basic_vehicle_status.fuel_range_elec = 32000
    message = MessageV2(MessageBodyV2(), vehicle_status_response)
    message_v2_1_coder.initialize_message(
        uid,
        token,
        vin_info.vin,
        "511",
        25857,
        1,
        message)
    return message_v2_1_coder.encode_request(message)


def mock_chrg_mgmt_data_rsp(message_v3_0_coder: MessageCoderV30, uid: str, token: str, vin_info: VinInfo) -> str:
    chrg_mgmt_data_rsp = OtaChrgMangDataResp()
    chrg_mgmt_data_rsp.bmsAdpPubChrgSttnDspCmd = 0
    chrg_mgmt_data_rsp.bmsAltngChrgCrntDspCmd = 0
    chrg_mgmt_data_rsp.bmsChrgCtrlDspCmd = 2
    chrg_mgmt_data_rsp.bmsChrgOtptCrntReq = 1023
    chrg_mgmt_data_rsp.bmsChrgSpRsn = 0
    chrg_mgmt_data_rsp.bmsChrgSts = 0
    chrg_mgmt_data_rsp.bmsEstdElecRng = 290
    chrg_mgmt_data_rsp.bmsOnBdChrgTrgtSOCDspCmd = 7
    chrg_mgmt_data_rsp.bmsPackCrnt = 20000
    chrg_mgmt_data_rsp.bmsPackSOCDsp = 841
    chrg_mgmt_data_rsp.bmsPackVol = 1602
    chrg_mgmt_data_rsp.bmsPTCHeatReqDspCmd = 0
    chrg_mgmt_data_rsp.bmsPTCHeatSpRsn = 0
    chrg_mgmt_data_rsp.bmsReserCtrlDspCmd = 0
    chrg_mgmt_data_rsp.bmsReserSpHourDspCmd = 0
    chrg_mgmt_data_rsp.bmsReserStHourDspCmd = 0
    chrg_mgmt_data_rsp.bmsReserStMintueDspCmd = 0
    chrg_mgmt_data_rsp.bmsReserSpMintueDspCmd = 0
    chrg_mgmt_data_rsp.chrgngRmnngTime = 1023
    chrg_mgmt_data_rsp.chrgngRmnngTimeV = 1
    chrg_mgmt_data_rsp.clstrElecRngToEPT = 243

    chrg_mgmt_data_rsp.chargeStatus = RvsChargingStatus()
    chrg_mgmt_data_rsp.chargeStatus.charging_duration = 0
    chrg_mgmt_data_rsp.chargeStatus.charging_gun_state = False
    chrg_mgmt_data_rsp.chargeStatus.fuel_Range_elec = 2430
    chrg_mgmt_data_rsp.chargeStatus.charging_type = 0
    chrg_mgmt_data_rsp.chargeStatus.mileage = 19320
    chrg_mgmt_data_rsp.chargeStatus.end_time = 1664974510
    chrg_mgmt_data_rsp.chargeStatus.last_charge_ending_power = 631
    chrg_mgmt_data_rsp.chargeStatus.mileage_of_day = 0
    chrg_mgmt_data_rsp.chargeStatus.mileage_since_last_charge = 120
    chrg_mgmt_data_rsp.chargeStatus.power_usage_of_day = 0
    chrg_mgmt_data_rsp.chargeStatus.power_usage_since_last_charge = 21
    chrg_mgmt_data_rsp.chargeStatus.real_time_power = 610
    chrg_mgmt_data_rsp.chargeStatus.start_time = 1664962716
    chrg_mgmt_data_rsp.chargeStatus.total_battery_capacity = 725
    chrg_mgmt_data_rsp.chargeStatus.working_current = 20000
    chrg_mgmt_data_rsp.chargeStatus.working_voltage = 1602

    chrg_mgmt_data_rsp_msg = MessageV30(MessageBodyV30(), chrg_mgmt_data_rsp)
    message_v3_0_coder.initialize_message(uid, token, vin_info.vin, '516', 768, 5, chrg_mgmt_data_rsp_msg)
    return message_v3_0_coder.encode_request(chrg_mgmt_data_rsp_msg)


def mock_response(mocked_post, hex_value: str):
    def res():
        r = requests.Response()
        r.status_code = 200
        return r

    mocked_post.return_value = res()
    type(mocked_post.return_value).content = PropertyMock(return_value=hex_value.encode())


class TestSaicApi(TestCase):
    def setUp(self) -> None:
        config = Configuration()
        config.saic_user = 'user@home.de'
        config.saic_password = 'secret'
        publisher = Logger(config)
        self.saic_api = SaicApi(config, publisher)
        self.message_coder_v1_1 = MessageCoderV11()
        self.message_coder_v2_1 = MessageCoderV21()
        self.message_coder_v3_0 = MessageCoderV30()

    @patch.object(requests, 'post')
    def test_login(self, mocked_post):
        mock_response(mocked_post, mock_login_response_hex(self.message_coder_v1_1))

        login_response_message = self.saic_api.login()
        self.assertIsNotNone(login_response_message.application_data)
        app_data = cast(MpUserLoggingInRsp, login_response_message.application_data)
        self.assertEqual('user_name', app_data.user_name)

    @patch.object(requests, 'post')
    def test_set_alarm_switches(self, mocked_post):
        mock_response(mocked_post, mock_alarm_switch_response_hex(self.message_coder_v1_1))

        try:
            self.saic_api.set_alarm_switches()
        except Exception:
            self.fail()

    @patch.object(requests, 'post')
    def test_get_vehicle_status(self, mocked_post):
        vin_info = create_vin_info(VIN)
        mock_response(mocked_post, mock_vehicle_status_response(self.message_coder_v2_1, UID, TOKEN, vin_info))

        vehicle_status_rsp_msg = self.saic_api.get_vehicle_status(vin_info)
        app_data = cast(OtaRvmVehicleStatusResp25857, vehicle_status_rsp_msg.application_data)
        self.assertEqual(1000000000, app_data.status_time)

    @patch.object(requests, 'post')
    def test_get_charging_status(self, mocked_post):
        vin_info = create_vin_info(VIN)
        mock_response(mocked_post, mock_chrg_mgmt_data_rsp(self.message_coder_v3_0, UID, TOKEN, vin_info))

        chrg_mgmt_data_rsp_msg = self.saic_api.get_charging_status(vin_info)
        app_data = cast(OtaChrgMangDataResp, chrg_mgmt_data_rsp_msg.application_data)
        self.assertEqual(1023, app_data.bmsChrgOtptCrntReq)
