import unittest

from configuration import Configuration, TransportProtocol
from publisher.mqtt_publisher import MqttClient, MqttCommandListener

USER = 'me@home.da'
VIN = 'vin10000000000000'
DELAY = '42'
MODE = 'periodic'
LOCK_STATE = 'true'
REAR_WINDOW_HEAT_STATE = 'on'


class TestMqttPublisher(unittest.IsolatedAsyncioTestCase, MqttCommandListener):
    async def on_mqtt_command_received(self, *, vin: str, topic: str, payload: str) -> None:
        self.received_vin = vin
        self.received_payload = payload.strip().lower()

    def setUp(self) -> None:
        config = Configuration()
        config.mqtt_topic = 'saic'
        config.saic_user = 'user+a#b*c>d$e'
        config.mqtt_transport_protocol = TransportProtocol.TCP
        self.mqtt_client = MqttClient(config)
        self.mqtt_client.command_listener = self
        self.received_vin = ''
        self.received_payload = ''
        self.vehicle_base_topic = f'{self.mqtt_client.configuration.mqtt_topic}/{USER}/vehicles/{VIN}'

    def test_special_character_username(self):
        self.assertEqual('saic/user_a_b_c_d_e', self.mqtt_client.get_mqtt_account_prefix())

    async def test_update_mode(self):
        topic = 'refresh/mode/set'
        full_topic = f'{self.vehicle_base_topic}/{topic}'
        await self.send_message(full_topic, MODE)
        self.assertEqual(VIN, self.received_vin)
        self.assertEqual(MODE, self.received_payload)

    async def test_update_lock_state(self):
        topic = 'doors/locked/set'
        full_topic = f'{self.vehicle_base_topic}/{topic}'
        await self.send_message(full_topic, LOCK_STATE)
        self.assertEqual(VIN, self.received_vin)
        self.assertEqual(LOCK_STATE, self.received_payload)

    async def test_update_rear_window_heat_state(self):
        topic = 'climate/rearWindowDefrosterHeating/set'
        full_topic = f'{self.vehicle_base_topic}/{topic}'
        await self.send_message(full_topic, REAR_WINDOW_HEAT_STATE)
        self.assertEqual(VIN, self.received_vin)
        self.assertEqual(REAR_WINDOW_HEAT_STATE, self.received_payload)

    async def send_message(self, topic, payload):
        await self.mqtt_client.client.on_message('client', topic, payload, 0, dict())
