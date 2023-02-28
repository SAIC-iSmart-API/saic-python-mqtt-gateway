import calendar
import time
from typing import cast
from unittest import TestCase

from saicapi.common_model import DataEncodingType, MessageCounter, BasicPosition, NetworkInfo, Header
from saicapi.ota_v1_1.Message import MessageCoderV11
from saicapi.ota_v1_1.data_model import MpUserLoggingInReq, MessageBodyV11, MessageV11, MessageListReq, StartEndNumber


class TestMessageCoderV11(TestCase):
    def setUp(self) -> None:
        self.message_coder = MessageCoderV11()

    def test_encode_login_request(self):
        expected_hex = '01F5111005600882CB162C58B162C58B162C58B162C58B162C58B162C58B162C58B162C58B162C58'\
                       + 'B162C58B162C58B162C58B161AB062C66C8240020200468ACF1343530ECA864468ACF1342468ACF1'\
                       + '342000001440100A08952A54A952A54AABAC30B162C586162C58B161858B162C30B162C587562C58'\
                       + '60C2C58B162FD8B162C58B0C1858B162C58B162C58BF62C586162C58B162C58B0B6C306161858B16'\
                       + '1830B162C30B162C58B162C586162C58B162C58617EFD8B162C586162C58B162C30B162C30B16183'\
                       + '0B162C58B162C58B162C58B162C306161858B162C58B162C58B161858B162C58B162C586162C58B0'\
                       + '8D1A3CBD796FE1971E1E4'
        header = Header()
        header.protocol_version = 17
        expected_message = MessageV11(header, MessageBodyV11(), MpUserLoggingInReq())
        self.message_coder.decode_response(expected_hex, expected_message)

        body = MessageBodyV11()
        body.application_data_encoding = DataEncodingType.PER_UNALIGNED.value
        body.application_data_length = 162
        body.application_data_protocol_version = 513
        body.application_id = '501'
        body.event_creation_time = calendar.timegm(time.strptime('2022-09-30 01:06:40', '%Y-%m-%d %H:%M:%S'))
        body.icc_id = '12345678901234567890'
        body.message_counter = MessageCounter()
        body.message_counter.downlink_counter = 0
        body.message_counter.uplink_counter = 1
        body.message_id = 1
        body.sim_info = '1234567890987654321'
        body.test_flag = 2
        body.uid = 'XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX'

        user_login_req = MpUserLoggingInReq()
        user_login_req.device_id = 'X0XXXX0XXXXX0XXXX0XXXX:XXX00XXXX_XXXXXX00XXXXXXXXX_XXX0XXXXXXXX-X00X0XXX00XXX0XX'\
                                   + 'XXXXXX0XXXXXXX0__XXXXX0XXXXXX0XXX0XX00XXXXXXXXXXXXXXX00X0XXXXXXXXXXX0XXXXXXXXX0X'\
                                   + 'XXX###europecar'
        user_login_req.password = '********'

        actual_message = MessageV11(header, body, user_login_req)
        actual_hex = self.message_coder.encode_request(actual_message)
        self.validate_message_body(cast(MessageBodyV11, expected_message.body),
                                   cast(MessageBodyV11, actual_message.body))
        self.assertEqual(expected_hex, actual_hex)

    def test_encode_message_list_request(self):
        expected_hex = '011B112007900C82C60C183060C183060C183060C183060C183060C183060C183060C183060C183'\
                       + '072C183060C183060E5CB972E5CB9B0E5CB973616B96162C2D72E6C395AE5CD872B5CD8B0E6C586'\
                       + '161CD87362C587361AB362C6A67E00020200468ACF134468ACF1342468ACF1342468ACF13420000'\
                       + '00240100A080000000000080000000000A120CC834A680'
        header = Header()
        header.protocol_version = 18
        expected_message = MessageV11(header, MessageBodyV11(), MessageListReq())
        self.message_coder.decode_response(expected_hex, expected_message)

        body = MessageBodyV11()
        body.application_data_encoding = DataEncodingType.PER_UNALIGNED.value
        body.application_data_length = 18
        body.application_data_protocol_version = 513
        body.application_id = '531'
        body.event_creation_time = calendar.timegm(time.strptime('2022-10-22 00:53:20', '%Y-%m-%d %H:%M:%S'))
        body.icc_id = '12345678901234567890'
        body.message_counter = MessageCounter()
        body.message_counter.downlink_counter = 0
        body.message_counter.uplink_counter = 1
        body.message_id = 1
        body.sim_info = '1234567891234567890'
        body.test_flag = 2
        body.token = '99X9999X-90XX-99X9-99X9-9XX9XX0X9X9XXX9X'
        body.uid = '00000000000000000000000000000000000090000000099999'

        message_list_req = MessageListReq()
        message_list_req.message_group = "ALARM"
        message_list_req.start_end_number = StartEndNumber()
        message_list_req.start_end_number.end_number = 20
        message_list_req.start_end_number.start_number = 1

        actual_message = MessageV11(header, body, message_list_req)
        actual_hex = self.message_coder.encode_request(actual_message)
        self.validate_message_body(cast(MessageBodyV11, expected_message.body),
                                   cast(MessageBodyV11, actual_message.body))
        self.assertEqual(expected_hex, actual_hex)

    def validate_message_body(self, expected: MessageBodyV11, actual: MessageBodyV11) -> None:
        self.assertEqual(expected.message_id, actual.message_id)
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
        if expected.message_counter is not None:
            self.validate_message_counter(expected.message_counter, actual.message_counter)
        else:
            self.assertIsNone(actual.message_counter)
        self.assertEqual(expected.icc_id, actual.icc_id)
        self.assertEqual(expected.sim_info, actual.sim_info)
        self.assertEqual(expected.stateless_dispatcher_message, actual.stateless_dispatcher_message)
        self.assertEqual(expected.crqm_request, actual.crqm_request)
        if expected.basic_position is not None:
            self.validate_basic_position(expected.basic_position, actual.basic_position)
        else:
            self.assertIsNone(actual.basic_position)
        if expected.network_info is not None:
            self.validate_network_info(expected.network_info, actual.network_info)
        else:
            self.assertIsNone(actual.network_info)
        self.assertEqual(expected.hmi_language, actual.hmi_language)

    def validate_message_counter(self, expected: MessageCounter, actual: MessageCounter) -> None:
        self.assertEqual(expected.downlink_counter, actual.downlink_counter)
        self.assertEqual(expected.uplink_counter, actual.uplink_counter)

    def validate_basic_position(self, expected: BasicPosition, actual: BasicPosition) -> None:
        self.assertEqual(expected.latitude, actual.latitude)
        self.assertEqual(expected.longitude, actual.longitude)

    def validate_network_info(self, expected: NetworkInfo, actual: NetworkInfo) -> None:
        self.assertEqual(expected.mcc_network, actual.mcc_network)
        self.assertEqual(expected.mnc_network, actual.mnc_network)
        self.assertEqual(expected.mcc_sim, actual.mcc_sim)
        self.assertEqual(expected.mnc_sim, actual.mnc_sim)
        self.assertEqual(expected.signal_strength, actual.signal_strength)
