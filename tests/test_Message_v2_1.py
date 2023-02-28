import calendar
import time
from typing import cast
from unittest import TestCase

from saicapi.common_model import DataEncodingType, MessageBodyV2, MessageV2
from saicapi.ota_v2_1.Message import MessageCoderV21
from saicapi.ota_v2_1.data_model import OtaRvcReq, RvcReqParam


class TestMessageCoderV21(TestCase):
    def setUp(self) -> None:
        self.message_coder = MessageCoderV21()

    def test_encode_ota_rvc_request(self):
        expected_hex = '1009E21790000000000000000000000000000000000FFF183060C183060C183060C183060C183060'\
                       + 'C183060C183060C183060C183060C1CB060C183060C183972E5CB97361CB9B0E5CD85B62C39B0B5C'\
                       + 'B9B1616B9B16182D72E5CD8B161CB97362C5872C1CB96AC5858B162C3972C1CB9B16183972E5CB90'\
                       + '1C6F2C94000009C3C00000000000000243280A0801800080008001000080018000807F80000'
        expected_message = MessageV2(MessageBodyV2(), OtaRvcReq())
        self.message_coder.decode_response(expected_hex, expected_message)

        reserved = bytes().fromhex('00000000000000000000000000000000')
        body = MessageBodyV2()
        body.ack_message_counter = 0
        body.ack_required = False
        body.application_data_encoding = DataEncodingType.PER_UNALIGNED.value
        body.application_data_length = 18
        body.application_data_protocol_version = 25857
        body.application_id = '510'
        body.dl_message_counter = 0
        body.event_creation_time = calendar.timegm(time.strptime('2022-11-19 23:20:00', '%Y-%m-%d %H:%M:%S'))
        body.event_id = 9999
        body.message_id = 1
        body.test_flag = 2
        body.token = '9X99X99X-XX9X-99XX-9XX0-999XXX999XXX9099'
        body.uid = '00000000000000000000000000000000000090000000099999'
        body.ul_message_counter = 0
        body.vin = 'XXXX99099XX099999'

        ota_rvc_req = get_ota_rvc_req_test_data()

        actual_message = MessageV2(body, ota_rvc_req, reserved)
        actual_hex = self.message_coder.encode_request(actual_message)
        self.validate_message_body(cast(MessageBodyV2, expected_message.body),
                                   cast(MessageBodyV2, actual_message.body))
        self.assertEqual(expected_hex, actual_hex)

    def validate_message_body(self, expected: MessageBodyV2, actual: MessageBodyV2) -> None:
        self.assertEqual(expected.message_id, actual.message_id)
        self.assertEqual(expected.ul_message_counter, actual.ul_message_counter)
        self.assertEqual(expected.dl_message_counter, actual.dl_message_counter)
        self.assertEqual(expected.ack_message_counter, actual.ack_message_counter)
        self.assertEqual(expected.event_creation_time, actual.event_creation_time)
        self.assertEqual(expected.application_id, actual.application_id)
        self.assertEqual(expected.application_data_protocol_version, actual.application_data_protocol_version)
        self.assertEqual(expected.test_flag, actual.test_flag)
        self.assertEqual(expected.uid, actual.uid)
        self.assertEqual(expected.token, actual.token)
        self.assertEqual(expected.event_id, actual.event_id)
        self.assertEqual(expected.application_data_encoding, actual.application_data_encoding)
        self.assertEqual(expected.application_data_length, actual.application_data_length)
        self.assertEqual(expected.vin, actual.vin)
        self.assertEqual(expected.ack_required, actual.ack_required)
        self.assertEqual(expected.result, actual.result)
        self.assertEqual(expected.error_message, actual.error_message)


def get_ota_rvc_req_test_data() -> OtaRvcReq:
    ota_rvc_req = OtaRvcReq()
    ota_rvc_req.rvc_req_type = b'\x00'

    param1 = RvcReqParam()
    param1.param_id = 1
    param1.param_value = b'\x01'
    ota_rvc_req.rvc_params.append(param1)

    param2 = RvcReqParam()
    param2.param_id = 2
    param2.param_value = b'\x01'
    ota_rvc_req.rvc_params.append(param2)

    param3 = RvcReqParam()
    param3.param_id = 3
    param3.param_value = b'\x01'
    ota_rvc_req.rvc_params.append(param3)

    param4 = RvcReqParam()
    param4.param_id = 255
    param4.param_value = b'\x00'
    ota_rvc_req.rvc_params.append(param4)

    return ota_rvc_req
