from unittest import TestCase

import paho.mqtt.client as mqtt

from mqtt_publisher import MqttClient
from saicapi.common_model import Configuration

USER = 'me@gome.da'
VIN = 'vin10000000000000'
DELAY = 42
MODE = 'periodic'


class TestMqttPublisher(TestCase):
    def __test_refresh_interval_update(self, seconds: int, vin: str):
        self.assertEqual(DELAY, seconds)
        self.assertEqual(VIN, vin)

    def __test_refresh_mode_update(self, mode: str, vin: str):
        self.assertEqual(MODE, mode)
        self.assertEqual(VIN, vin)

    def setUp(self) -> None:
        config = Configuration()
        config.mqtt_topic = 'saic'
        config.mqtt_transport_protocol = 'tcp'
        self.mqtt_client = MqttClient(config)
        self.mqtt_client.on_refresh_mode_update = self.__test_refresh_mode_update
        self.mqtt_client.on_active_refresh_interval_update = self.__test_refresh_interval_update
        self.mqtt_client.on_inactive_refresh_interval_update = self.__test_refresh_interval_update

    def test_update_mode(self):
        topic = f'{self.mqtt_client.configuration.mqtt_topic}/{USER}/vehicles/{VIN}/refresh/mode/set'
        msg = mqtt.MQTTMessage(topic=bytes(topic, encoding='utf8'))
        msg.payload = bytes(MODE, encoding='utf8')
        self.mqtt_client.client.on_message('client', 'userdata', msg)
