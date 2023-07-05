from unittest import TestCase

import paho.mqtt.client as mqtt

from configuration import Configuration
from mqtt_publisher import MqttClient

USER = 'me@home.da'
VIN = 'vin10000000000000'
DELAY = '42'
MODE = 'periodic'
LOCK_STATE = 'true'
REAR_WINDOW_HEAT_STATE = 'on'


class TestMqttPublisher(TestCase):
    def __test_mqtt_command_received(self, vin: str, msg: mqtt.MQTTMessage) -> None:
        self.received_vin = vin
        self.received_payload = msg.payload.decode().strip().lower()

    def setUp(self) -> None:
        config = Configuration()
        config.mqtt_topic = 'saic'
        config.mqtt_transport_protocol = 'tcp'
        self.mqtt_client = MqttClient(config)
        self.mqtt_client.on_mqtt_command_received = self.__test_mqtt_command_received
        self.received_vin = ''
        self.received_payload = ''
        self.vehicle_base_topic = f'{self.mqtt_client.configuration.mqtt_topic}/{USER}/vehicles/{VIN}'

    def test_update_mode(self):
        topic = 'refresh/mode/set'
        full_topic = f'{self.vehicle_base_topic}/{topic}'
        msg = mqtt.MQTTMessage(topic=bytes(full_topic, encoding='utf8'))
        msg.payload = bytes(MODE, encoding='utf8')
        self.send_message(msg)
        self.assertEqual(VIN, self.received_vin)
        self.assertEqual(MODE, self.received_payload)

    def test_update_lock_state(self):
        topic = 'doors/locked/set'
        full_topic = f'{self.vehicle_base_topic}/{topic}'
        msg = mqtt.MQTTMessage(topic=bytes(full_topic, encoding='utf8'))
        msg.payload = bytes(LOCK_STATE, encoding='utf8')
        self.send_message(msg)
        self.assertEqual(VIN, self.received_vin)
        self.assertEqual(LOCK_STATE, self.received_payload)

    def test_update_rear_window_heat_state(self):
        topic = 'climate/rearWindowDefrosterHeating/set'
        full_topic = f'{self.vehicle_base_topic}/{topic}'
        msg = mqtt.MQTTMessage(topic=bytes(full_topic, encoding='utf8'))
        msg.payload = bytes(REAR_WINDOW_HEAT_STATE, encoding='utf8')
        self.send_message(msg)
        self.assertEqual(VIN, self.received_vin)
        self.assertEqual(REAR_WINDOW_HEAT_STATE, self.received_payload)

    def send_message(self, message: mqtt.MQTTMessage):
        self.mqtt_client.client.on_message('client', 'userdata', message)
