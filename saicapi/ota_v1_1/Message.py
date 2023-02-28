from saicapi.common_model import MessageCoderV1
from saicapi.ota_v1_1.data_model import MessageV11


class MessageCoderV11(MessageCoderV1):
    def __init__(self):
        super().__init__('ASN.1_schema/v1_1/')

    def encode_request(self, message: MessageV11) -> str:
        return super().encode_request(message)

    def decode_response(self, message: str, decoded_message: MessageV11) -> None:
        super().decode_response(message, decoded_message)

    def initialize_message(self, uid: str, token: str, application_id: str,
                           application_data_protocol_version: int, message_id: int, message: MessageV11,
                           vin: str = None):
        super().initialize_message(uid, token, vin, application_id, application_data_protocol_version, message_id,
                                   message)
