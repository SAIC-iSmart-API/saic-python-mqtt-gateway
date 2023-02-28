import json
import logging
import re

import paho.mqtt.client as mqtt
from saicapi.common_model import Configuration


class Publisher:
    def __init__(self, config: Configuration):
        self.configuration = config

    def publish_json(self, key: str, data: dict) -> None:
        pass

    def publish_str(self, key: str, value: str) -> None:
        pass

    def publish_int(self, key: str, value: int) -> None:
        pass

    def publish_bool(self, key: str, value: bool) -> None:
        pass

    def publish_float(self, key: str, value: float) -> None:
        pass

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
                        data[key] = self.anonymize_str(data[key])
                    case 'email':
                        data[key] = self.anonymize_str(data[key])
                    case 'uid':
                        data[key] = self.anonymize_str(data[key])
                    case 'pin':
                        data[key] = self.anonymize_str(data[key])
                    case'token':
                        data[key] = self.anonymize_str(data[key])
                    case 'refreshToken':
                        data[key] = self.anonymize_str(data[key])
                    case 'vin':
                        data[key] = self.anonymize_str(data[key])
                    case 'deviceId':
                        data[key] = self.anonymize_device_id(data[key])
                    case 'seconds':
                        data[key] = self.anonymize_int(data[key])
                    case 'bindTime':
                        data[key] = self.anonymize_int(data[key])
                    case 'eventCreationTime':
                        data[key] = self.anonymize_int(data[key])
                    case 'latitude':
                        data[key] = self.anonymize_int(data[key])
                    case 'longitude':
                        data[key] = self.anonymize_int(data[key])
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

    def anonymize_str(self, value: str) -> str:
        r = re.sub('[a-zA-Z]', 'X', value)
        return re.sub('[1-9]', '9', r)

    def anonymize_device_id(self, device_id: str) -> str:
        elements = device_id.split('###')
        return f'{self.anonymize_str(elements[0])}###{self.anonymize_str(elements[1])}'

    def anonymize_int(self, value: int) -> int:
        return int(value / 100000 * 100000)

    def dict_to_anonymized_json(self, data):
        no_binary_strings = self.remove_byte_strings(data)
        if self.configuration.anonymized_publishing:
            result = self.anonymize(no_binary_strings)
        else:
            result = no_binary_strings
        return json.dumps(result)


class MqttClient(Publisher):
    def __init__(self, configuration: Configuration):
        super().__init__(configuration)
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.configuration = configuration
        self.topic_root = configuration.mqtt_topic

    def on_connect(self, client, userdata, flags, rc) -> None:
        print(f'Connected with result code {rc}')

    def on_message(self, client, userdata, msg: mqtt.MQTTMessage) -> None:
        print(f'{msg.topic} {msg.payload}')

    def publish(self, msg: mqtt.MQTTMessage) -> None:
        self.client.publish(msg.topic, msg.payload, retain=True)

    def get_topic(self, key: str) -> bytes:
        return bytes(f'{self.topic_root}/{key}')

    def publish_json(self, key: str, data: dict) -> None:
        msg = mqtt.MQTTMessage(topic=self.get_topic(key))
        msg.payload = bytes(self.dict_to_anonymized_json(data))
        self.publish(msg)

    def publish_str(self, key: str, value: str) -> None:
        msg = mqtt.MQTTMessage(topic=self.get_topic(key))
        msg.payload = bytes(value)
        self.publish(msg)

    def publish_int(self, key: str, value: int) -> None:
        msg = mqtt.MQTTMessage(topic=self.get_topic(key))
        msg.payload = bytes(value)
        self.publish(msg)

    def publish_bool(self, key: str, value: bool) -> None:
        msg = mqtt.MQTTMessage(topic=self.get_topic(key))
        msg.payload = bytes(value)
        self.publish(msg)

    def publish_float(self, key: str, value: float) -> None:
        msg = mqtt.MQTTMessage(topic=self.get_topic(key))
        msg.payload = value
        self.publish(msg)


class Logger(Publisher):
    def __init__(self, configuration: Configuration):
        super().__init__(configuration)
        logging.basicConfig(format='%(asctime)s %(message)s', level=logging.DEBUG)

    def publish_json(self, key: str, data: dict) -> None:
        logging.debug(f'{key}: {self.dict_to_anonymized_json(data)}')

    def publish_str(self, key: str, value: str) -> None:
        logging.debug(f'{key}: {value}')

    def publish_int(self, key: str, value: int) -> None:
        logging.debug(f'{key}: {value}')

    def publish_bool(self, key: str, value: bool) -> None:
        logging.debug(f'{key}: {value}')

    def publish_float(self, key: str, value: float) -> None:
        logging.debug(f'{key}: {value}')
