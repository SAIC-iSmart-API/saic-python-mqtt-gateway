import threading
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
        self.is_connected = threading.Event()
        self.client = None
        self.host = self.configuration.mqtt_host
        self.port = self.configuration.mqtt_port
        self.transport_protocol = self.configuration.mqtt_transport_protocol

        mqtt_client = mqtt.Client(str(self.publisher_id), transport=self.transport_protocol)
        mqtt_client.on_connect = self.__on_connect
        mqtt_client.on_message = self.__on_message
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
        # wait until we've connected
        self.is_connected.wait()

    def __on_connect(self, client, userdata, flags, rc) -> None:
        if rc == mqtt.CONNACK_ACCEPTED:
            self.is_connected.set()
        else:
            SystemExit(f'Unable to connect to MQTT brocker. Return code: {rc}')

    def __on_message(self, client, userdata, msg: mqtt.MQTTMessage) -> None:
        print(f'{msg.topic} {msg.payload}')

    def publish(self, msg: mqtt.MQTTMessage) -> None:
        self.client.publish(msg.topic, msg.payload, retain=True)

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
