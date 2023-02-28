from saicapi.common_model import MessageCoderV2, MessageV2


class MessageCoderV21(MessageCoderV2):
    def __init__(self):
        super().__init__('ASN.1_schema/v2_1/')

    def encode_request(self, message: MessageV2) -> str:
        return super().encode_request(message)

    def decode_response(self, message: str, decoded_message: MessageV2) -> None:
        return super().decode_response(message, decoded_message)

    def initialize_message(self, uid: str, token: str, vin: str, application_id: str,
                           application_data_protocol_version: int, message_id: int, message: MessageV2) -> None:
        return super().initialize_message(uid, token, vin, application_id, application_data_protocol_version,
                                          message_id, message)

    def get_protocol_version(self) -> int:
        return 33
