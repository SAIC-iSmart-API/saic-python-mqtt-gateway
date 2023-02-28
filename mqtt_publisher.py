import urllib.parse
import uuid
import paho.mqtt.client as mqtt

from saicapi.common_model import Configuration
from saicapi.publisher import Publisher


class MqttClient(Publisher):
    def __init__(self, configuration: Configuration):
        super().__init__(configuration)
        self.publisher_id = uuid.uuid4()
        self.configuration = configuration
        self.topic_root = configuration.mqtt_topic
        self.connected = False
        self.client = None
        self.host = ''
        self.port = -1
        self.transport_protocol = ''

        self.init_mqtt_connection_data(self.configuration.mqtt_uri)
        mqtt_client = mqtt.Client(str(self.publisher_id), transport=self.transport_protocol)
        mqtt_client.on_connect = self.on_connect
        mqtt_client.on_message = self.on_message
        self.client = mqtt_client

    def connect(self):
        if self.configuration.mqtt_user is not None:
            if self.configuration.mqtt_password is not None:
                self.client.username_pw_set(username=self.configuration.mqtt_user,
                                            password=self.configuration.mqtt_password)
            else:
                self.client.username_pw_set(username=self.configuration.mqtt_user)
        self.client.connect(host=self.host, port=self.port)
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, rc) -> None:
        if rc == 0:
            self.connected = True
        else:
            SystemExit(f'Unable to connect to MQTT brocker. Return code: {rc}')

    def on_message(self, client, userdata, msg: mqtt.MQTTMessage) -> None:
        print(f'{msg.topic} {msg.payload}')

    def publish(self, msg: mqtt.MQTTMessage) -> None:
        if self.connected:
            self.client.publish(msg.topic, msg.payload, retain=True)
        else:
            raise SystemExit('MQTT connection lost')

    def get_topic(self, key: str) -> bytes:
        return bytes(f'{self.topic_root}/{key}', encoding='utf8')

    def publish_json(self, key: str, data: dict) -> None:
        msg = mqtt.MQTTMessage(topic=self.get_topic(key))
        msg.payload = bytes(self.dict_to_anonymized_json(data), encoding='utf8')
        self.publish(msg)

    def publish_str(self, key: str, value: str) -> None:
        msg = mqtt.MQTTMessage(topic=self.get_topic(key))
        msg.payload = bytes(value, encoding='utf8')
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

    def init_mqtt_connection_data(self, mqtt_uri: str):
        parse_result = urllib.parse.urlparse(mqtt_uri)
        if parse_result.scheme == 'tcp':
            self.transport_protocol = 'tcp'
        elif parse_result.scheme == 'ws':
            self.transport_protocol = 'websockets'
        else:
            raise SystemExit(f'Invalid MQTT URI scheme: {parse_result.scheme}, use tcp or ws')

        if not parse_result.port:
            if self.transport_protocol == 'tcp':
                self.port = 1883
            else:
                self.port = 9001

        self.host = str(parse_result.hostname)
