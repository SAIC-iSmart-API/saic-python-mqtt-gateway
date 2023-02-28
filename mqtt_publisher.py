import uuid
import paho.mqtt.client as mqtt

from saicapi.common_model import Configuration
from saicapi.publisher import Publisher


class MqttClient(Publisher):
    def __init__(self, configuration: Configuration):
        super().__init__(configuration)
        self.publisher_id =  uuid.uuid4()
        self.client = mqtt.Client(str(self.publisher_id))
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.configuration = configuration
        self.topic_root = configuration.mqtt_topic
        self.connected = False

    def on_connect(self, client, userdata, flags, rc) -> None:
        print(f'Connected with result code {rc}')

    def on_message(self, client, userdata, msg: mqtt.MQTTMessage) -> None:
        print(f'{msg.topic} {msg.payload}')

    def publish(self, msg: mqtt.MQTTMessage) -> None:
        if not self.connected:
            self.client.connect(self.configuration.mqtt_uri)
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
