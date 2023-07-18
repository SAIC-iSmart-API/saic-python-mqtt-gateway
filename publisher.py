import json
import re

from configuration import Configuration


class Publisher:
    def __init__(self, config: Configuration):
        self.configuration = config
        self.mode_by_vin = {}
        self.map = {}

    def publish_json(self, key: str, data: dict, no_prefix: bool = False) -> None:
        self.map[key] = data

    def publish_str(self, key: str, value: str, no_prefix: bool = False) -> None:
        self.map[key] = value

    def publish_int(self, key: str, value: int, no_prefix: bool = False) -> None:
        self.map[key] = value

    def publish_bool(self, key: str, value: bool, no_prefix: bool = False) -> None:
        self.map[key] = value

    def publish_float(self, key: str, value: float, no_prefix: bool = False) -> None:
        self.map[key] = value

    def reset_force_mode(self, vin: str, refresh_mode: str) -> None:
        topic = f'{self.configuration.saic_user}/vehicles/{vin}/refresh/mode/set'
        if (
                vin in self.mode_by_vin
                and self.mode_by_vin[vin] == 'force'
        ):
            self.publish_str(topic, refresh_mode)

    def remove_byte_strings(self, data: dict) -> dict:
        for key in data.keys():
            if isinstance(data[key], bytes):
                data[key] = str(data[key])
            elif isinstance(data[key], dict):
                data[key] = self.remove_byte_strings(data[key])
            elif isinstance(data[key], list):
                for item in data[key]:
                    if isinstance(item, dict):
                        self.remove_byte_strings(item)
        return data

    def anonymize(self, data: dict) -> dict:
        for key in data.keys():
            if isinstance(data[key], str):
                match key:
                    case 'password':
                        data[key] = '******'
                    case 'uid':
                        data[key] = Publisher.anonymize_str(data[key])
                    case 'email':
                        data[key] = Publisher.anonymize_str(data[key])
                    case 'uid':
                        data[key] = Publisher.anonymize_str(data[key])
                    case 'pin':
                        data[key] = Publisher.anonymize_str(data[key])
                    case 'token':
                        data[key] = Publisher.anonymize_str(data[key])
                    case 'refreshToken':
                        data[key] = Publisher.anonymize_str(data[key])
                    case 'vin':
                        data[key] = Publisher.anonymize_str(data[key])
                    case 'deviceId':
                        data[key] = self.anonymize_device_id(data[key])
                    case 'seconds':
                        data[key] = Publisher.anonymize_int(data[key])
                    case 'bindTime':
                        data[key] = Publisher.anonymize_int(data[key])
                    case 'eventCreationTime':
                        data[key] = Publisher.anonymize_int(data[key])
                    case 'latitude':
                        data[key] = Publisher.anonymize_int(data[key])
                    case 'longitude':
                        data[key] = Publisher.anonymize_int(data[key])
                    case 'eventID':
                        data[key] = 9999
                    case 'lastKeySeen':
                        data[key] = 9999
                    case 'content':
                        data[key] = re.sub('\\(\\*\\*\\*...\\)', '(***XXX)', data[key])
            elif isinstance(data[key], dict):
                data[key] = self.anonymize(data[key])
            elif isinstance(data[key], list):
                for item in data[key]:
                    if isinstance(item, dict):
                        data[key] = self.anonymize(item)
        return data

    @staticmethod
    def anonymize_str(value: str) -> str:
        r = re.sub('[a-zA-Z]', 'X', value)
        return re.sub('[1-9]', '9', r)

    def anonymize_device_id(self, device_id: str) -> str:
        elements = device_id.split('###')
        return f'{self.anonymize_str(elements[0])}###{self.anonymize_str(elements[1])}'

    @staticmethod
    def anonymize_int(value: int) -> int:
        return int(value / 100000 * 100000)

    def dict_to_anonymized_json(self, data):
        no_binary_strings = self.remove_byte_strings(data)
        if self.configuration.anonymized_publishing:
            result = self.anonymize(no_binary_strings)
        else:
            result = no_binary_strings
        return json.dumps(result, indent=2)
