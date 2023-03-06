import io
import os
import pathlib
import time
from enum import Enum

import asn1tools
from asn1tools.compiler import Specification

FIELD_ERROR_MESSAGE = 'errorMessage'
FIELD_RESULT = 'result'
FIELD_TEST_FLAG = 'testFlag'
FIELD_APPLICATION_DATA_ENCODING = 'applicationDataEncoding'
FIELD_ACK_REQUIRED = 'ackRequired'
FIELD_EVENT_ID = 'eventID'
FIELD_VIN = 'vin'
FIELD_TOKEN = 'token'
FIELD_UID = 'uid'
FIELD_APPLICATION_DATA_PROTOCOL_VERSION = 'applicationDataProtocolVersion'
FIELD_APPLICATION_DATA_LENGTH = 'applicationDataLength'
FIELD_MESSAGE_ID = 'messageID'
FIELD_EVENT_CREATION_TIME = 'eventCreationTime'
FIELD_APPLICATION_ID = 'applicationID'
FIELD_ACK_MESSAGE_COUNTER = 'ackMessageCounter'
FIELD_DL_MESSAGE_COUNTER = 'dlMessageCounter'
FIELD_UL_MESSAGE_COUNTER = 'ulMessageCounter'
FIELD_ICC_ID = 'iccID'
FIELD_HMI_LANGUAGE = 'hmiLanguage'
FIELD_NETWORK_INFO = 'networkInfo'
FIELD_BASIC_POSITION = 'basicPosition'
FIELD_CRQM_REQUEST = 'crqmRequest'
FIELD_STATE_LESS_DISPATCHER_MESSAGE = 'statelessDispatcherMessage'
FIELD_SIM_INFO = 'simInfo'
FIELD_MESSAGE_COUNTER = 'messageCounter'
FIELD_DOWNLINK_COUNTER = 'downlinkCounter'
FIELD_UPLINK_COUNTER = 'uplinkCounter'
FIELD_LONGITUDE = 'longitude'
FIELD_LATITUDE = 'latitude'
FIELD_MNC_SIM = 'mncSim'
FIELD_MCC_SIM = 'mccSim'
FIELD_MNC_NETWORK = 'mncNetwork'
FIELD_MCC_NETWORK = 'mccNetwork'
FIELD_SIGNAL_STRENGTH = 'signalStrength'


class Configuration:
    def __init__(self):
        self.saic_user = ''
        self.saic_password = ''
        self.saic_uri = ''
        self.abrp_token_map = {}
        self.abrp_api_key = ''
        self.mqtt_host = ''
        self.mqtt_port = -1
        self.mqtt_transport_protocol = ''
        self.mqtt_user = ''
        self.mqtt_password = ''
        self.mqtt_topic = ''
        self.openwb_topic = ''
        self.anonymized_publishing = False
        self.inactive_vehicle_state_refresh_interval = 900  # in seconds
        self.messages_request_interval = 5  # in seconds


class Header:
    def __init__(self):
        self.protocol_version = None
        self.security_context = None
        self.dispatcher_message_length = None
        self.dispatcher_body_encoding = None

    def get_body_encoding_int_value(self) -> int:
        if self.dispatcher_body_encoding == DataEncodingType.PER_UNALIGNED:
            return 0
        elif self.dispatcher_body_encoding == DataEncodingType.DER:
            return 1
        elif self.dispatcher_body_encoding == DataEncodingType.BER:
            return 1
        else:
            return -1

    def get_data(self) -> dict:
        data = {
            'protocolVersion': self.protocol_version,
            'dispatcherMessageLength': self.dispatcher_message_length
        }
        if self.dispatcher_body_encoding is not None:
            data['dispatcherBodyEncoding'] = self.dispatcher_body_encoding
        if self.security_context is not None:
            data['securityContext'] = self.security_context
        return data


class Asn1Type:
    def __init__(self, asn_type: str):
        self.asn_type = asn_type

    def get_data(self) -> dict:
        pass

    def init_from_dict(self, data: dict):
        pass

    def add_optional_field_to_data(self, data: dict, key: str, value) -> None:
        if value is not None:
            data[key] = value


class AbstractMessageBody(Asn1Type):
    def __init__(self, asn_type: str):
        super().__init__(asn_type)
        self.message_id = None
        self.event_creation_time = None
        self.application_id = None
        self.application_data_protocol_version = None
        self.test_flag = None
        self.uid = None
        self.token = None
        self.event_id = None
        self.application_data_encoding = None
        self.application_data_length = None
        self.vin = None
        self.ack_required = None
        self.result = None
        self.error_message = None

    def get_data(self) -> dict:
        data = {
            FIELD_APPLICATION_ID: self.application_id,
            FIELD_EVENT_CREATION_TIME: self.event_creation_time,
            FIELD_MESSAGE_ID: self.message_id,
            FIELD_APPLICATION_DATA_LENGTH: self.application_data_length,
            FIELD_APPLICATION_DATA_PROTOCOL_VERSION: self.application_data_protocol_version
        }
        self.add_optional_field_to_data(data, FIELD_UID, self.uid)
        self.add_optional_field_to_data(data, FIELD_TOKEN, self.token)
        self.add_optional_field_to_data(data, FIELD_VIN, self.vin)
        self.add_optional_field_to_data(data, FIELD_EVENT_ID, self.event_id)
        self.add_optional_field_to_data(data, FIELD_ACK_REQUIRED, self.ack_required)
        if self.application_data_encoding is not None:
            data[FIELD_APPLICATION_DATA_ENCODING] = self.application_data_encoding
        self.add_optional_field_to_data(data, FIELD_TEST_FLAG, self.test_flag)
        self.add_optional_field_to_data(data, FIELD_RESULT, self.result)
        self.add_optional_field_to_data(data, FIELD_ERROR_MESSAGE, self.error_message)

        return data

    def init_from_dict(self, data: dict):
        self.uid = data.get(FIELD_UID)
        self.token = data.get(FIELD_TOKEN)
        self.application_id = data.get(FIELD_APPLICATION_ID)
        self.vin = data.get(FIELD_VIN)
        self.event_creation_time = data.get(FIELD_EVENT_CREATION_TIME)
        self.event_id = data.get(FIELD_EVENT_ID)
        self.message_id = data.get(FIELD_MESSAGE_ID)
        self.ack_required = data.get(FIELD_ACK_REQUIRED)
        self.application_data_length = data.get(FIELD_APPLICATION_DATA_LENGTH)
        self.application_data_encoding = data.get(FIELD_APPLICATION_DATA_ENCODING)
        self.application_data_protocol_version = data.get(FIELD_APPLICATION_DATA_PROTOCOL_VERSION)
        self.test_flag = data.get(FIELD_TEST_FLAG)
        self.result = data.get(FIELD_RESULT)
        self.error_message = data.get(FIELD_ERROR_MESSAGE)


class MessageBodyV1(AbstractMessageBody):
    def __init__(self, asn_type: str):
        super().__init__(asn_type)
        self.message_counter = None
        self.icc_id = None
        self.sim_info = None
        self.stateless_dispatcher_message = None
        self.crqm_request = None
        self.basic_position = None
        self.network_info = None
        self.hmi_language = None

    def get_data(self) -> dict:
        data = super().get_data()
        data[FIELD_ICC_ID] = self.icc_id
        self.add_optional_field_to_data(data, FIELD_STATE_LESS_DISPATCHER_MESSAGE, self.stateless_dispatcher_message)
        self.add_optional_field_to_data(data, FIELD_CRQM_REQUEST, self.crqm_request)
        if self.basic_position is not None:
            data[FIELD_BASIC_POSITION] = self.basic_position.get_data()
        if self.network_info is not None:
            data[FIELD_NETWORK_INFO] = self.network_info.get_data()
        self.add_optional_field_to_data(data, FIELD_SIM_INFO, self.sim_info)
        if self.hmi_language is not None:
            data[FIELD_HMI_LANGUAGE] = self.hmi_language.get_data()
        if self.message_counter is not None:
            data[FIELD_MESSAGE_COUNTER] = self.message_counter.get_data()
        return data

    def init_from_dict(self, data: dict):
        super().init_from_dict(data)
        if FIELD_MESSAGE_COUNTER in data:
            self.message_counter = MessageCounter()
            self.message_counter.init_from_dict(data.get(FIELD_MESSAGE_COUNTER))
        self.stateless_dispatcher_message = data.get(FIELD_STATE_LESS_DISPATCHER_MESSAGE)
        self.crqm_request = data.get(FIELD_CRQM_REQUEST)
        if FIELD_BASIC_POSITION in data:
            self.basic_position = BasicPosition()
            self.basic_position.init_from_dict(data.get(FIELD_BASIC_POSITION))
        if FIELD_NETWORK_INFO in data:
            self.network_info = NetworkInfo()
            self.network_info.init_from_dict(data.get(FIELD_NETWORK_INFO))
        self.sim_info = data.get(FIELD_SIM_INFO)
        if FIELD_HMI_LANGUAGE in data:
            self.hmi_language = data.get(FIELD_HMI_LANGUAGE)
        self.icc_id = data.get(FIELD_ICC_ID)


class MessageBodyV2(AbstractMessageBody):
    def __init__(self):
        super().__init__('MPDispatcherBody')
        self.ul_message_counter = None
        self.dl_message_counter = None
        self.ack_message_counter = None

    def get_data(self) -> dict:
        data = super().get_data()
        self.add_optional_field_to_data(data, FIELD_UL_MESSAGE_COUNTER, self.ul_message_counter)
        self.add_optional_field_to_data(data, FIELD_DL_MESSAGE_COUNTER, self.dl_message_counter)
        self.add_optional_field_to_data(data, FIELD_ACK_MESSAGE_COUNTER, self.ack_message_counter)
        return data

    def init_from_dict(self, data: dict):
        super().init_from_dict(data)
        self.ul_message_counter = data.get(FIELD_UL_MESSAGE_COUNTER)
        self.dl_message_counter = data.get(FIELD_DL_MESSAGE_COUNTER)
        self.ack_message_counter = data.get(FIELD_ACK_MESSAGE_COUNTER)


class ApplicationData(Asn1Type):
    def __init__(self, asn_type: str):
        super().__init__(asn_type)


class AbstractMessage:
    def __init__(self, header: Header, body: AbstractMessageBody, application_data: ApplicationData):
        self.header = header
        self.body = body
        self.application_data = application_data

    def get_version(self) -> str:
        pass

    def get_data(self) -> dict:
        app_data = None
        if (
                self.application_data is not None
                and self.application_data.get_data()
        ):
            app_data = self.application_data.get_data()
        return {
            'applicationData': app_data,
            'body': self.body.get_data(),
            'header': self.header.get_data()
        }


class MessageV1(AbstractMessage):
    def __init__(self, header: Header, body: MessageBodyV1, application_data: ApplicationData = None):
        super().__init__(header, body, application_data)


class MessageV2(AbstractMessage):
    def __init__(self, body: MessageBodyV2, application_data: ApplicationData = None,
                 reserved: bytes = None):
        super().__init__(Header(), body, application_data)
        self.reserved = reserved


class AbstractMessageCoder:
    def __init__(self, asn_files_dir: str):
        self.asn_files = []
        self.asn_files_dir = pathlib.Path(__file__).parent / asn_files_dir
        self.load_asn_files()

    def load_asn_files(self):
        for f in os.listdir(self.asn_files_dir):
            if f.endswith('.asn1'):
                self.asn_files.append(str(self.asn_files_dir) + '/' + f)

    def encode_request(self, message: AbstractMessage) -> str:
        pass

    def decode_response(self, message: str, decoded_message: AbstractMessage) -> None:
        pass

    def initialize_message(self, uid: str, token: str, vin: str, application_id: str,
                           application_data_protocol_version: int, message_id: int, message: AbstractMessage) -> None:
        pass

    def get_current_time(self) -> int:
        return int(time.time())

    def get_application_data_bytes(self, application_data: ApplicationData, asn1_tool: Specification) -> bytes:
        if application_data is not None:
            application_data_bytes = asn1_tool.encode(application_data.asn_type, application_data.get_data())
        else:
            application_data_bytes = bytes()
        return application_data_bytes


class MessageCoderV1(AbstractMessageCoder):
    def __init__(self, asn_files_dir: str):
        super().__init__(asn_files_dir)
        self.asn1_tool_uper = asn1tools.compile_files(self.asn_files, 'uper')
        self.header_length = 4

    def encode_request(self, message: MessageV1) -> str:
        application_data_bytes = self.get_application_data_bytes(message.application_data, self.asn1_tool_uper)

        message_body = message.body
        message_body.application_data_encoding = DataEncodingType.PER_UNALIGNED.value
        message_body.application_data_length = len(application_data_bytes)

        message_body_bytes = self.asn1_tool_uper.encode(message_body.asn_type, message_body.get_data())

        message_header = message.header
        if message_header.protocol_version is None:
            raise ValueError('Protocol version in header missing')
        message_header.security_context = 0
        message_header.dispatcher_message_length = len(message_body_bytes) + self.header_length
        message_header.dispatcher_body_encoding = DataEncodingType.PER_UNALIGNED

        buffered_message_bytes = io.BytesIO()
        buffered_message_bytes.write(message_header.protocol_version.to_bytes(1, "little"))
        buffered_message_bytes.write(message_header.security_context.to_bytes(1, "little"))
        buffered_message_bytes.write(message_header.dispatcher_message_length.to_bytes(1, "little"))
        buffered_message_bytes.write(message_header.get_body_encoding_int_value().to_bytes(1, "little"))

        buffered_message_bytes.write(message_body_bytes)

        buffered_message_bytes.write(application_data_bytes)

        message_bytes = buffered_message_bytes.getvalue()

        length_hex = "{:04x}".format(len(message_bytes) * 2 + 5)
        result = length_hex + "1" + message_bytes.hex()
        return result.upper()

    def decode_response(self, message: str, decoded_message: MessageV1) -> None:
        buffered_message_bytes = io.BytesIO(bytes.fromhex(message[5:]))

        header_bytes = buffered_message_bytes.read(self.header_length)
        decoded_message.header.protocol_version = int(header_bytes[0])
        decoded_message.header.security_context = int(header_bytes[1])
        decoded_message.header.dispatcher_message_length = int(header_bytes[2])
        decoded_message.header.dispatcher_body_encoding = int(header_bytes[3])

        dispatcher_message_bytes = buffered_message_bytes.read(
            decoded_message.header.dispatcher_message_length - self.header_length)
        message_body = decoded_message.body
        message_body_dict = self.asn1_tool_uper.decode(message_body.asn_type, dispatcher_message_bytes)
        message_body.init_from_dict(message_body_dict)

        if decoded_message.body.application_data_length > 0:
            application_data_bytes = buffered_message_bytes.read(decoded_message.body.application_data_length)
            application_data_dict = self.asn1_tool_uper.decode(decoded_message.application_data.asn_type,
                                                               application_data_bytes)
            decoded_message.application_data.init_from_dict(application_data_dict)
        else:
            decoded_message.application_data = None

    def initialize_message(self, uid: str, token: str, vin: str, application_id: str,
                           application_data_protocol_version: int, message_id: int, message: MessageV1):
        message_counter = MessageCounter()
        message_counter.downlink_counter = 0
        message_counter.uplink_counter = 1

        body = message.body
        body.message_counter = message_counter
        body.message_id = message_id
        body.icc_id = '12345678901234567890'
        body.sim_info = '1234567890987654321'
        body.event_creation_time = self.get_current_time()
        body.application_id = application_id
        body.application_data_protocol_version = application_data_protocol_version
        body.test_flag = 2
        body.uid = uid
        body.token = token
        body.vin = vin
        body.event_id = 0


class MessageCoderV2(AbstractMessageCoder):
    def __init__(self, asn_files_dir: str):
        super().__init__(asn_files_dir)
        self.asn1_tool_uper = asn1tools.compile_files(self.asn_files, 'uper')
        self.header_length = 3
        self.reserved_size = 16

    def encode_request(self, message: MessageV2) -> str:
        application_data_bytes = self.get_application_data_bytes(message.application_data, self.asn1_tool_uper)

        message_body = message.body
        message_body.application_data_encoding = DataEncodingType.PER_UNALIGNED.value
        message_body.application_data_length = len(application_data_bytes)

        message_body_bytes = self.asn1_tool_uper.encode(message_body.asn_type, message_body.get_data())

        message_header = message.header
        message_header.protocol_version = self.get_protocol_version()
        message_header.dispatcher_message_length = len(message_body_bytes) + self.header_length
        message_header.dispatcher_body_encoding = DataEncodingType.PER_UNALIGNED

        buffered_message_bytes = io.BytesIO()
        buffered_message_bytes.write(message_header.protocol_version.to_bytes(1, 'little'))
        buffered_message_bytes.write(message_header.dispatcher_message_length.to_bytes(1, 'little'))
        buffered_message_bytes.write(message_header.get_body_encoding_int_value().to_bytes(1, 'little'))

        buffered_message_bytes.write(message.reserved)

        buffered_message_bytes.write(message_body_bytes)

        buffered_message_bytes.write(application_data_bytes)

        message_bytes = buffered_message_bytes.getvalue()

        length_hex = "{:04x}".format(len(message_bytes) + self.header_length)
        result = "1" + length_hex + message_bytes.hex()
        return result.upper()

    def decode_response(self, message: str, decoded_message: MessageV2) -> None:
        buffered_message_bytes = io.BytesIO(bytes.fromhex(message[5:]))

        header = decoded_message.header
        header_bytes = buffered_message_bytes.read(self.header_length)
        header.protocol_version = int(header_bytes[0])
        header.dispatcher_message_length = int(header_bytes[1])
        header.dispatcher_body_encoding = int(header_bytes[2])

        decoded_message.reserved = buffered_message_bytes.read(self.reserved_size)

        dispatcher_message_bytes = buffered_message_bytes.read(header.dispatcher_message_length - self.header_length)
        message_body_dict = self.asn1_tool_uper.decode('MPDispatcherBody', dispatcher_message_bytes)
        message_body = decoded_message.body
        message_body.init_from_dict(message_body_dict)

        if message_body.application_data_length > 0:
            application_data_bytes = buffered_message_bytes.read(message_body.application_data_length)
            application_data_dict = self.asn1_tool_uper.decode(decoded_message.application_data.asn_type,
                                                               application_data_bytes)
            decoded_message.application_data.init_from_dict(application_data_dict)
        else:
            decoded_message.application_data = None

    def initialize_message(self, uid: str, token: str, vin: str, application_id: str,
                           application_data_protocol_version: int, message_id: int, message: MessageV2) -> None:
        message.body.message_id = message_id
        message.body.ul_message_counter = 0
        message.body.dl_message_counter = 0
        message.body.ack_message_counter = 0
        message.body.event_creation_time = self.get_current_time()
        message.body.application_id = application_id
        message.body.application_data_protocol_version = application_data_protocol_version
        message.body.test_flag = 2
        message.body.uid = uid
        message.body.token = token
        message.body.vin = vin
        message.body.event_id = 0
        message.body.result = 0

        message.reserved = bytes(self.reserved_size)

    def get_protocol_version(self) -> int:
        pass


class DataEncodingType(Enum):
    PER_UNALIGNED = 'perUnaligned'
    DER = 'der'
    BER = 'ber'


class MessageCounter(Asn1Type):
    def __init__(self):
        super().__init__('MessageCounter')
        self.downlink_counter = None
        self.uplink_counter = None

    def get_data(self) -> dict:
        return {
            FIELD_UPLINK_COUNTER: self.uplink_counter,
            FIELD_DOWNLINK_COUNTER: self.downlink_counter
        }

    def init_from_dict(self, data: dict):
        self.uplink_counter = data.get(FIELD_UPLINK_COUNTER)
        self.downlink_counter = data.get(FIELD_DOWNLINK_COUNTER)


class BasicPosition(Asn1Type):
    def __init__(self):
        super().__init__('BasicPosition')
        self. latitude = None
        self.longitude = None

    def get_data(self) -> dict:
        return {
            FIELD_LATITUDE: self.latitude,
            FIELD_LONGITUDE: self.longitude
        }

    def init_from_dict(self, data: dict):
        self.latitude = data.get(FIELD_LATITUDE)
        self.longitude = data.get(FIELD_LONGITUDE)


class NetworkInfo(Asn1Type):
    def __init__(self):
        super().__init__('NetworkInfo')
        self.mcc_network = None
        self.mnc_network = None
        self.mcc_sim = None
        self.mnc_sim = None
        self.signal_strength = None

    def get_data(self) -> dict:
        return {
            FIELD_MCC_NETWORK: self.mcc_network,
            FIELD_MNC_NETWORK: self.mnc_network,
            FIELD_MCC_SIM: self.mcc_sim,
            FIELD_MNC_SIM: self.mnc_sim,
            FIELD_SIGNAL_STRENGTH: self.signal_strength
        }

    def init_from_dict(self, data: dict):
        self.mcc_network = data.get(FIELD_MCC_NETWORK)
        self.mnc_network = data.get(FIELD_MNC_NETWORK)
        self.mcc_sim = data.get(FIELD_MCC_SIM)
        self.mnc_sim = data.get(FIELD_MNC_SIM)
        self.signal_strength = data.get(FIELD_SIGNAL_STRENGTH)
