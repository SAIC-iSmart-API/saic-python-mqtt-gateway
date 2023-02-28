from saicapi.common_model import ApplicationData, MessageV2, MessageCoderV2, MessageBodyV2


class MessageBodyV30(MessageBodyV2):
    def __init__(self):
        super().__init__()

    def ack_message_counter_present(self) -> bool:
        return self.ack_message_counter is not None

    def ack_required_present(self) -> bool:
        return self.ack_required is not None

    def application_data_encoding_present(self) -> bool:
        return self.application_data_encoding is not None

    def application_data_length_present(self) -> bool:
        return self.application_data_length is not None

    def application_data_protocol_version_present(self) -> bool:
        return self.application_data_protocol_version is not None

    def dl_message_counter_present(self) -> bool:
        return self.dl_message_counter is not None

    def ul_message_counter_present(self) -> bool:
        return self.ul_message_counter is not None

    def error_message_present(self) -> bool:
        return self.error_message is not None

    def event_id_present(self) -> bool:
        return self.event_id is not None

    def test_flag_present(self) -> bool:
        return self.test_flag is not None

    def token_present(self) -> bool:
        return self.token is not None

    def uid_present(self) -> bool:
        return self.uid is not None

    def vin_present(self) -> bool:
        return self.vin is not None


class MessageV30(MessageV2):
    def __init__(self, body: MessageBodyV30, application_data: ApplicationData = None,
                 reserved: bytes = None):
        super().__init__(body, application_data, reserved)


class MessageCoderV30(MessageCoderV2):
    def __init__(self):
        super().__init__('ASN.1_schema/v3_0/')

    def encode_request(self, message: MessageV30) -> str:
        return super().encode_request(message)

    def decode_response(self, message: str, decoded_message: MessageV30) -> None:
        super().decode_response(message, decoded_message)

    def initialize_message(self, uid: str, token: str, vin: str, application_id: str,
                           application_data_protocol_version: int, message_id: int, message: MessageV30) -> None:
        return super().initialize_message(uid, token, vin, application_id, application_data_protocol_version,
                                          message_id, message)

    def get_protocol_version(self) -> int:
        return 48
