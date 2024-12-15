import json
import re
from abc import ABC
from typing import Optional

import mqtt_topics
from configuration import Configuration

INVALID_MQTT_CHARS = re.compile(r'[^a-zA-Z0-9/]')


class MqttCommandListener(ABC):
    async def on_mqtt_command_received(self, *, vin: str, topic: str, payload: str) -> None:
        raise NotImplementedError("Should have implemented this")

    async def on_charging_detected(self, vin: str) -> None:
        raise NotImplementedError("Should have implemented this")


class Publisher(ABC):
    def __init__(self, config: Configuration):
        self.__configuration = config
        self.__command_listener = None
        self.__topic_root = self.__remove_special_mqtt_characters(config.mqtt_topic)

    async def connect(self):
        pass

    def is_connected(self) -> bool:
        raise NotImplementedError()

    def publish_json(self, key: str, data: dict, no_prefix: bool = False) -> None:
        raise NotImplementedError()

    def publish_str(self, key: str, value: str, no_prefix: bool = False) -> None:
        raise NotImplementedError()

    def publish_int(self, key: str, value: int, no_prefix: bool = False) -> None:
        raise NotImplementedError()

    def publish_bool(self, key: str, value: bool | int | None, no_prefix: bool = False) -> None:
        raise NotImplementedError()

    def publish_float(self, key: str, value: float, no_prefix: bool = False) -> None:
        raise NotImplementedError()

    def get_mqtt_account_prefix(self) -> str:
        return self.__remove_special_mqtt_characters(
            f'{self.__topic_root}/{self.configuration.saic_user}'
        )

    def get_topic(self, key: str, no_prefix: bool) -> str:
        if no_prefix:
            topic = key
        else:
            topic = f'{self.__topic_root}/{key}'
        return self.__remove_special_mqtt_characters(topic)

    def __remove_special_mqtt_characters(self, input_str: str) -> str:
        return INVALID_MQTT_CHARS.sub('_', input_str)

    def __remove_byte_strings(self, data: dict) -> dict:
        for key in data.keys():
            if isinstance(data[key], bytes):
                data[key] = str(data[key])
            elif isinstance(data[key], dict):
                data[key] = self.__remove_byte_strings(data[key])
            elif isinstance(data[key], list):
                for item in data[key]:
                    if isinstance(item, dict):
                        self.__remove_byte_strings(item)
        return data

    def __anonymize(self, data: dict) -> dict:
        if isinstance(data, dict):
            for key in data.keys():
                if isinstance(data[key], str):
                    match key:
                        case 'password':
                            data[key] = '******'
                        case 'uid' | 'email' | 'user_name' | 'account' | 'ping' | 'token' | 'access_token' | 'refreshToken' | 'refresh_token' | 'vin':
                            data[key] = Publisher.anonymize_str(data[key])
                        case 'deviceId':
                            data[key] = self.anonymize_device_id(data[key])
                        case 'seconds' | 'bindTime' | 'eventCreationTime' | 'latitude' | 'longitude':
                            data[key] = Publisher.anonymize_int(data[key])
                        case 'eventID' | 'event-id' | 'event_id' | 'eventId' | 'event_id' | 'eventID' | 'lastKeySeen':
                            data[key] = 9999
                        case 'content':
                            data[key] = re.sub('\\(\\*\\*\\*...\\)', '(***XXX)', data[key])
                elif isinstance(data[key], dict):
                    data[key] = self.__anonymize(data[key])
                elif isinstance(data[key], (list, set, tuple)):
                    data[key] = [self.__anonymize(item) for item in data[key]]
        return data

    def keepalive(self):
        self.publish_str(mqtt_topics.INTERNAL_LWT, 'online', False)

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
        no_binary_strings = self.__remove_byte_strings(data)
        if self.configuration.anonymized_publishing:
            result = self.__anonymize(no_binary_strings)
        else:
            result = no_binary_strings
        return json.dumps(result, indent=2)

    @property
    def configuration(self) -> Configuration:
        return self.__configuration

    @property
    def command_listener(self) -> Optional[MqttCommandListener]:
        return self.__command_listener

    @command_listener.setter
    def command_listener(self, listener: MqttCommandListener):
        self.__command_listener = listener
