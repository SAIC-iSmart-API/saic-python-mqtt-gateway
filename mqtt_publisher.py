import threading
import uuid
import paho.mqtt.client as mqtt

import mqtt_topics
from configuration import Configuration
from publisher import Publisher


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
        self.on_mqtt_command_received = None

        mqtt_client = mqtt.Client(str(self.publisher_id), transport=self.transport_protocol, protocol=mqtt.MQTTv31)
        mqtt_client.on_connect = self.__on_connect
        mqtt_client.on_message = self.__on_message
        self.client = mqtt_client

    def get_mqtt_account_prefix(self) -> str:
        return f'{self.configuration.mqtt_topic}/{self.configuration.saic_user}'

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

            mqtt_account_prefix = self.get_mqtt_account_prefix()
            self.client.subscribe(f'{mqtt_account_prefix}/{mqtt_topics.VEHICLES}/+/+/+/set')
            self.client.subscribe(f'{mqtt_account_prefix}/{mqtt_topics.VEHICLES}/+/+/+/+/set')
            self.client.subscribe(f'{mqtt_account_prefix}/{mqtt_topics.VEHICLES}/+/{mqtt_topics.REFRESH_MODE}/set')
            self.client.subscribe(f'{mqtt_account_prefix}/{mqtt_topics.VEHICLES}/+/{mqtt_topics.REFRESH_PERIOD}/+/set')
            self.client.subscribe(f'{self.configuration.open_wb_topic}/lp/+/boolChargeStat')
        else:
            SystemExit(f'Unable to connect to MQTT broker. Return code: {rc}')

    def __on_message(self, client, userdata, msg: mqtt.MQTTMessage) -> None:
        if msg.topic.endswith('/boolChargeStat'):
            index = self.get_index_from_open_wp_topic(msg.topic)
            if index in self.configuration.open_wb_lp_map:
                vin = self.configuration.open_wb_lp_map[index]
                if msg.payload.decode() == '1':
                    mqtt_account_prefix = self.get_mqtt_account_prefix()
                    topic = f'{mqtt_account_prefix}/{mqtt_topics.VEHICLES}/{vin}/{mqtt_topics.REFRESH_MODE}/set'
                    m = mqtt.MQTTMessage(msg.mid, topic.encode())
                    m.payload = str.encode('force')
                    self.on_mqtt_command_received(vin, m)
            else:
                self.on_mqtt_command_received('', msg)

        else:
            vin = self.get_vin_from_topic(msg.topic)
            if self.on_mqtt_command_received is not None:
                self.on_mqtt_command_received(vin, msg)
        return

    def publish(self, msg: mqtt.MQTTMessage) -> None:
        self.client.publish(msg.topic, msg.payload, retain=True)

    def get_topic(self, key: str, no_prefix: bool) -> bytes:
        if no_prefix:
            topic = bytes(f'{key}', encoding='utf8')
        else:
            topic = bytes(f'{self.topic_root}/{key}', encoding='utf8')
        return topic

    def publish_json(self, key: str, data: dict, no_prefix: bool = False) -> None:
        msg = mqtt.MQTTMessage(topic=self.get_topic(key, no_prefix))
        msg.payload = bytes(self.dict_to_anonymized_json(data), encoding='utf8')
        self.publish(msg)

    def publish_str(self, key: str, value: str, no_prefix: bool = False) -> None:
        msg = mqtt.MQTTMessage(topic=self.get_topic(key, no_prefix))
        msg.payload = bytes(value, encoding='utf8')
        self.publish(msg)

    def publish_int(self, key: str, value: int, no_prefix: bool = False) -> None:
        msg = mqtt.MQTTMessage(topic=self.get_topic(key, no_prefix))
        msg.payload = value
        self.publish(msg)

    def publish_bool(self, key: str, value: bool, no_prefix: bool = False) -> None:
        msg = mqtt.MQTTMessage(topic=self.get_topic(key, no_prefix))
        msg.payload = value
        self.publish(msg)

    def publish_float(self, key: str, value: float, no_prefix: bool = False) -> None:
        msg = mqtt.MQTTMessage(topic=self.get_topic(key, no_prefix))
        msg.payload = value
        self.publish(msg)

    def get_vin_from_topic(self, topic: str) -> str:
        global_topic_removed = topic[len(self.configuration.mqtt_topic) + 1:]
        elements = global_topic_removed.split('/')
        return elements[2]

    def get_index_from_open_wp_topic(self, topic: str):
        open_wb_topic_removed = topic[len(f'{self.configuration.open_wb_topic}') + 1:]
        elements = open_wb_topic_removed.split('/')
        return elements[1]
