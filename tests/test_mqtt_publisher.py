from unittest import TestCase

import paho.mqtt.client as mqtt

from configuration import Configuration
from mqtt_publisher import MqttClient

USER = 'me@home.da'
VIN = 'vin10000000000000'
DELAY = 42
MODE = 'periodic'
LOCK_STATE = 'True'
REAR_WINDOW_HEAT_STATE = 'on'


class TestMqttPublisher(TestCase):
    def __test_refresh_interval_update(self, seconds: int, vin: str):
        self.assertEqual(DELAY, seconds)
        self.assertEqual(VIN, vin)
        self.message_processed = True

    def __test_refresh_mode_update(self, mode: str, vin: str):
        self.assertEqual(MODE, mode)
        self.assertEqual(VIN, vin)
        self.message_processed = True

    def __test_doors_lock_state_update(self, lock_state: str, vin: str):
        self.assertEqual(LOCK_STATE, str(lock_state))
        self.assertEqual(VIN, vin)
        self.message_processed = True

    def __test_update_rear_window_heat_state(self, rear_window_heat_state: str, vin: str):
        self.assertEqual(REAR_WINDOW_HEAT_STATE, rear_window_heat_state)
        self.assertEqual(VIN, vin)
        self.message_processed = True

    def setUp(self) -> None:
        config = Configuration()
        config.mqtt_topic = 'saic'
        config.mqtt_transport_protocol = 'tcp'
        self.mqtt_client = MqttClient(config)
        self.mqtt_client.on_refresh_mode_update = self.__test_refresh_mode_update
        self.mqtt_client.on_active_refresh_interval_update = self.__test_refresh_interval_update
        self.mqtt_client.on_inactive_refresh_interval_update = self.__test_refresh_interval_update
        self.mqtt_client.on_doors_lock_state_update = self.__test_doors_lock_state_update
        self.mqtt_client.on_rear_window_heat_state_update = self.__test_update_rear_window_heat_state
        self.vehicle_base_topic = f'{self.mqtt_client.configuration.mqtt_topic}/{USER}/vehicles/{VIN}'

    def test_update_mode(self):
        topic = f'{self.vehicle_base_topic}/refresh/mode/set'
        msg = mqtt.MQTTMessage(topic=bytes(topic, encoding='utf8'))
        msg.payload = bytes(MODE, encoding='utf8')
        self.send_message(msg)

    def test_update_lock_state(self):
        topic = f'{self.vehicle_base_topic}/doors/locked/set'
        msg = mqtt.MQTTMessage(topic=bytes(topic, encoding='utf8'))
        msg.payload = bytes(LOCK_STATE, encoding='utf8')
        self.send_message(msg)

    def test_update_rear_window_heat_state(self):
        topic = f'{self.vehicle_base_topic}/climate/rearWindowDefrosterHeating/set'
        msg = mqtt.MQTTMessage(topic=bytes(topic, encoding='utf8'))
        msg.payload = bytes(REAR_WINDOW_HEAT_STATE, encoding='utf8')
        self.send_message(msg)

    def send_message(self, message: mqtt.MQTTMessage):
        self.message_processed = False
        self.mqtt_client.client.on_message('client', 'userdata', message)
        self.assertEqual(True, self.message_processed)
