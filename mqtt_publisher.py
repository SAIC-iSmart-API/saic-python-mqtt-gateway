import logging
import os
import threading
import paho.mqtt.client as mqtt

import mqtt_topics
from configuration import Configuration
from publisher import Publisher

LOG = logging.getLogger(__name__)
LOG.setLevel(level=os.getenv('LOG_LEVEL', 'INFO').upper())

MQTT_LOG = logging.getLogger(mqtt.__name__)
MQTT_LOG.setLevel(level=os.getenv('MQTT_LOG_LEVEL', 'INFO').upper())


class MqttClient(Publisher):
    def __init__(self, configuration: Configuration):
        super().__init__(configuration)
        self.configuration = configuration
        self.publisher_id = self.configuration.mqtt_client_id
        self.topic_root = configuration.mqtt_topic
        self.is_connected = threading.Event()
        self.client = None
        self.host = self.configuration.mqtt_host
        self.port = self.configuration.mqtt_port
        self.transport_protocol = self.configuration.mqtt_transport_protocol
        self.on_mqtt_command_received = None
        self.vin_by_charge_state_topic = {}
        self.vin_by_charger_connected_topic = {}

        mqtt_client = mqtt.Client(str(self.publisher_id), transport=self.transport_protocol.transport_mechanism,
                                  protocol=mqtt.MQTTv311)
        mqtt_client.enable_logger(MQTT_LOG)
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
        self.client.will_set(
            self.get_topic(mqtt_topics.INTERNAL_LWT, False).decode('utf8'),
            payload='offline',
            retain=True
        )
        if self.transport_protocol.with_tls:
            cert_uri = self.configuration.tls_server_cert_path
            LOG.debug(f'Configuring network encryption and authentication options for MQTT using {cert_uri}')
            self.client.tls_set(ca_certs=cert_uri)
            self.client.tls_insecure_set(True)
        self.client.connect(host=self.host, port=self.port)
        self.client.loop_start()
        # wait until we've connected
        self.is_connected.wait()

    def __on_connect(self, client, userdata, flags, rc) -> None:
        if rc == mqtt.CONNACK_ACCEPTED:
            LOG.info('Connected to MQTT broker')
            self.is_connected.set()
            mqtt_account_prefix = self.get_mqtt_account_prefix()
            self.client.subscribe(f'{mqtt_account_prefix}/{mqtt_topics.VEHICLES}/+/+/+/set')
            self.client.subscribe(f'{mqtt_account_prefix}/{mqtt_topics.VEHICLES}/+/+/+/+/set')
            self.client.subscribe(f'{mqtt_account_prefix}/{mqtt_topics.VEHICLES}/+/{mqtt_topics.REFRESH_MODE}/set')
            self.client.subscribe(f'{mqtt_account_prefix}/{mqtt_topics.VEHICLES}/+/{mqtt_topics.REFRESH_PERIOD}/+/set')
            for charging_station in self.configuration.charging_stations_by_vin.values():
                LOG.debug(f'Subscribing to MQTT topic {charging_station.charge_state_topic}')
                self.vin_by_charge_state_topic[charging_station.charge_state_topic] = charging_station.vin
                self.client.subscribe(charging_station.charge_state_topic)
                if charging_station.connected_topic:
                    LOG.debug(f'Subscribing to MQTT topic {charging_station.connected_topic}')
                    self.vin_by_charger_connected_topic[charging_station.connected_topic] = charging_station.vin
                    self.client.subscribe(charging_station.connected_topic)
            self.keepalive()
        else:
            SystemExit(f'Unable to connect to MQTT broker. Return code: {rc}')

    def __on_message(self, client, userdata, msg: mqtt.MQTTMessage) -> None:
        try:
            self.__on_message_real(client, userdata, msg)
        except Exception as e:
            LOG.exception(f'Error while processing MQTT message: {e}')

    def __on_message_real(self, client, userdata, msg: mqtt.MQTTMessage) -> None:
        if msg.topic in self.vin_by_charge_state_topic:
            payload = msg.payload.decode()
            LOG.debug(f'Received message over topic {msg.topic} with payload {payload}')
            vin = self.vin_by_charge_state_topic[msg.topic]
            charging_station = self.configuration.charging_stations_by_vin[vin]
            if payload == charging_station.charging_value:
                LOG.debug(f'Vehicle with vin {vin} is charging. Setting refresh mode to force')
                mqtt_account_prefix = self.get_mqtt_account_prefix()
                topic = f'{mqtt_account_prefix}/{mqtt_topics.VEHICLES}/{vin}/{mqtt_topics.REFRESH_MODE}/set'
                m = mqtt.MQTTMessage(msg.mid, topic.encode())
                m.payload = str.encode('force')
                self.on_mqtt_command_received(vin, m)
        elif msg.topic in self.vin_by_charger_connected_topic:
            payload = msg.payload.decode()
            LOG.debug(f'Received message over topic {msg.topic} with payload {payload}')
            vin = self.vin_by_charger_connected_topic[msg.topic]
            charging_station = self.configuration.charging_stations_by_vin[vin]
            if payload == charging_station.connected_value:
                LOG.debug(f'Vehicle with vin {vin} is connected to its charging station')
            else:
                LOG.debug(f'Vehicle with vin {vin} is disconnected from its charging station')
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
