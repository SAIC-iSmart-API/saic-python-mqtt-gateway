import calendar
import time
from typing import cast
from unittest import TestCase

from saicapi.common_model import DataEncodingType
from saicapi.ota_v3_0.Message import MessageCoderV30, MessageBodyV30, MessageV30
from saicapi.ota_v3_0.data_model import OtaChrgMangDataResp, RvsChargingStatus


class TestMessageCoderV30(TestCase):
    def setUp(self):
        self.message_coder = MessageCoderV30()

    def test_encode_chrg_mgmt_data(self):
        expected_hex = '100CF30750000000000000000000000000000000000F0F983060C183060C183060C183060C18306'\
                       + '0C183060C183060C183060C183060C1CB060C183060C183972E5CB97361CB972E5CB95AC2C39B0B'\
                       + '5CB073616B972E5CAD72E6C5872E6C39B0E6C5872E5CB96AC5B58B162C3972C1CB9B16183972E5C'\
                       + 'B906C67BC48000009C3C011C03004000000800000000000000070122000203FF0103FF4E2006420'\
                       + '349000000F30000CFCE0026204BF00633D509CC67AFD5C9C400C8400F0002A00000000000000000'\
                       + '9DC0B5400025BC0000'
        expected_message = MessageV30(MessageBodyV30(), OtaChrgMangDataResp())
        self.message_coder.decode_response(expected_hex, expected_message)

        reserved = bytes().fromhex('00000000000000000000000000000000')
        body = MessageBodyV30()
        body.application_data_encoding = DataEncodingType.PER_UNALIGNED.value
        body.application_data_length = 71
        body.application_data_protocol_version = 768
        body.application_id = '516'
        body.event_creation_time = calendar.timegm(time.strptime('2022-10-05 20:00:00', '%Y-%m-%d %H:%M:%S'))
        body.event_id = 9999
        body.message_id = 6
        body.result = 0
        body.test_flag = 2
        body.token = '9X999999-0X9X-909X-9999-99XX99X9X9XX9999'
        body.uid = '00000000000000000000000000000000000090000000099999'
        body.vin = 'XXXX99099XX099999'

        chrg_mgmt_data_rsp = get_chrg_mgmt_data_rsp_test_data()

        actual_message = MessageV30(body, chrg_mgmt_data_rsp, reserved)
        actual_hex = self.message_coder.encode_request(actual_message)
        self.validate_message(expected_message, actual_message)
        self.assertEqual(expected_hex, actual_hex)

    def validate_message(self, expected: MessageV30, actual: MessageV30) -> None:
        self.assertEqual(expected.body.application_data_encoding, actual.body.application_data_encoding)
        self.assertEqual(expected.body.application_data_length, actual.body.application_data_length)
        self.assertEqual(expected.body.application_data_protocol_version, actual.body.application_data_protocol_version)
        self.assertEqual(expected.body.application_id, actual.body.application_id)
        self.assertEqual(expected.body.event_creation_time, actual.body.event_creation_time)
        self.assertEqual(expected.body.event_id, actual.body.event_id)
        self.assertEqual(expected.body.message_id, actual.body.message_id)
        self.assertEqual(expected.body.test_flag, actual.body.test_flag)
        self.assertEqual(expected.body.token, actual.body.token)
        self.assertEqual(expected.body.uid, actual.body.uid)
        self.assertEqual(expected.body.vin, actual.body.vin)

        self.validate_chrg_mgmt_data(cast(OtaChrgMangDataResp, expected.application_data),
                                     cast(OtaChrgMangDataResp, actual.application_data))

    def validate_chrg_mgmt_data(self, expected: OtaChrgMangDataResp, actual: OtaChrgMangDataResp):
        self.assertEqual(expected.bmsAdpPubChrgSttnDspCmd, actual.bmsAdpPubChrgSttnDspCmd)
        self.assertEqual(expected.bmsAltngChrgCrntDspCmd, actual.bmsAltngChrgCrntDspCmd)
        self.assertEqual(expected.bmsChrgCtrlDspCmd, actual.bmsChrgCtrlDspCmd)
        self.assertEqual(expected.bmsChrgOtptCrntReq, actual.bmsChrgOtptCrntReq)
        self.assertEqual(expected.bmsChrgSpRsn, actual.bmsChrgSpRsn)
        self.assertEqual(expected.bmsChrgSts, actual.bmsChrgSts)
        self.assertEqual(expected.bmsEstdElecRng, actual.bmsEstdElecRng)
        self.assertEqual(expected.bmsOnBdChrgTrgtSOCDspCmd, actual.bmsOnBdChrgTrgtSOCDspCmd)
        self.assertEqual(expected.bmsPackCrnt, actual.bmsPackCrnt)
        self.assertEqual(expected.bmsPackSOCDsp, actual.bmsPackSOCDsp)
        self.assertEqual(expected.bmsPackVol, actual.bmsPackVol)
        self.assertEqual(expected.bmsPTCHeatReqDspCmd, actual.bmsPTCHeatReqDspCmd)
        self.assertEqual(expected.bmsPTCHeatSpRsn, actual.bmsPTCHeatSpRsn)
        self.assertEqual(expected.bmsReserCtrlDspCmd, actual.bmsReserCtrlDspCmd)
        self.assertEqual(expected.bmsReserSpHourDspCmd, actual.bmsReserSpHourDspCmd)
        self.assertEqual(expected.bmsReserStHourDspCmd, actual.bmsReserStHourDspCmd)
        self.assertEqual(expected.bmsReserStMintueDspCmd, actual.bmsReserStMintueDspCmd)
        self.assertEqual(expected.bmsReserSpMintueDspCmd, actual.bmsReserSpMintueDspCmd)
        self.assertEqual(expected.chrgngRmnngTime, actual.chrgngRmnngTime)
        self.assertEqual(expected.chrgngRmnngTimeV, actual.chrgngRmnngTimeV)
        self.assertEqual(expected.clstrElecRngToEPT, actual.clstrElecRngToEPT)
        self.validate_chrg_status(expected.chargeStatus, actual.chargeStatus)

    def validate_chrg_status(self, expected: RvsChargingStatus, actual: RvsChargingStatus):
        self.assertEqual(expected.charging_duration, actual.charging_duration)
        self.assertEqual(expected.charging_gun_state, actual.charging_gun_state)
        self.assertEqual(expected.fuel_Range_elec, actual.fuel_Range_elec)
        self.assertEqual(expected.charging_type, actual.charging_type)
        self.assertEqual(expected.mileage, actual.mileage)
        self.assertEqual(expected.end_time, actual.end_time)
        self.assertEqual(expected.last_charge_ending_power, actual.last_charge_ending_power)
        self.assertEqual(expected.mileage_of_day, actual.mileage_of_day)
        self.assertEqual(expected.mileage_since_last_charge, actual.mileage_since_last_charge)
        self.assertEqual(expected.power_usage_of_day, actual.power_usage_of_day)
        self.assertEqual(expected.power_usage_since_last_charge, actual.power_usage_since_last_charge)
        self.assertEqual(expected.real_time_power, actual.real_time_power)
        self.assertEqual(expected.start_time, actual.start_time)
        self.assertEqual(expected.total_battery_capacity, actual.total_battery_capacity)
        self.assertEqual(expected.working_current, actual.working_current)
        self.assertEqual(expected.working_voltage, actual.working_voltage)


def get_chrg_mgmt_data_rsp_test_data() -> OtaChrgMangDataResp:
    chrg_mgmt_data = OtaChrgMangDataResp()
    chrg_mgmt_data.bmsAdpPubChrgSttnDspCmd = 0
    chrg_mgmt_data.bmsAltngChrgCrntDspCmd = 0
    chrg_mgmt_data.bmsChrgCtrlDspCmd = 2
    chrg_mgmt_data.bmsChrgOtptCrntReq = 1023
    chrg_mgmt_data.bmsChrgSpRsn = 0
    chrg_mgmt_data.bmsChrgSts = 0
    chrg_mgmt_data.bmsEstdElecRng = 290
    chrg_mgmt_data.bmsOnBdChrgTrgtSOCDspCmd = 7
    chrg_mgmt_data.bmsPackCrnt = 20000
    chrg_mgmt_data.bmsPackSOCDsp = 841
    chrg_mgmt_data.bmsPackVol = 1602
    chrg_mgmt_data.bmsPTCHeatReqDspCmd = 0
    chrg_mgmt_data.bmsPTCHeatSpRsn = 0
    chrg_mgmt_data.bmsReserCtrlDspCmd = 0
    chrg_mgmt_data.bmsReserSpHourDspCmd = 0
    chrg_mgmt_data.bmsReserStHourDspCmd = 0
    chrg_mgmt_data.bmsReserStMintueDspCmd = 0
    chrg_mgmt_data.bmsReserSpMintueDspCmd = 0
    chrg_mgmt_data.chrgngRmnngTime = 1023
    chrg_mgmt_data.chrgngRmnngTimeV = 1
    chrg_mgmt_data.clstrElecRngToEPT = 243

    chrg_mgmt_data.chargeStatus = RvsChargingStatus()
    chrg_mgmt_data.chargeStatus.charging_duration = 0
    chrg_mgmt_data.chargeStatus.charging_gun_state = False
    chrg_mgmt_data.chargeStatus.fuel_Range_elec = 2430
    chrg_mgmt_data.chargeStatus.charging_type = 0
    chrg_mgmt_data.chargeStatus.mileage = 19320
    chrg_mgmt_data.chargeStatus.end_time = 1664974510
    chrg_mgmt_data.chargeStatus.last_charge_ending_power = 631
    chrg_mgmt_data.chargeStatus.mileage_of_day = 0
    chrg_mgmt_data.chargeStatus.mileage_since_last_charge = 120
    chrg_mgmt_data.chargeStatus.power_usage_of_day = 0
    chrg_mgmt_data.chargeStatus.power_usage_since_last_charge = 21
    chrg_mgmt_data.chargeStatus.real_time_power = 610
    chrg_mgmt_data.chargeStatus.start_time = 1664962716
    chrg_mgmt_data.chargeStatus.total_battery_capacity = 725
    chrg_mgmt_data.chargeStatus.working_current = 20000
    chrg_mgmt_data.chargeStatus.working_voltage = 1602

    return chrg_mgmt_data
