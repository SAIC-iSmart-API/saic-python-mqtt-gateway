import unittest

from apscheduler.schedulers.blocking import BlockingScheduler
from saic_ismart_client_ng.api.vehicle.schema import VinInfo

import mqtt_topics
from configuration import Configuration
from . import MessageCapturingConsolePublisher
from .common_mocks import VIN, get_mock_vehicle_status_resp, DRIVETRAIN_SOC_BMS, DRIVETRAIN_RANGE_BMS, \
    DRIVETRAIN_SOC_VEHICLE, DRIVETRAIN_RANGE_VEHICLE, get_moc_charge_management_data_resp
from vehicle import VehicleState


class TestVehicleState(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        config = Configuration()
        config.anonymized_publishing = False
        publisher = MessageCapturingConsolePublisher(config)
        vin_info = VinInfo()
        vin_info.vin = VIN
        account_prefix = f'/vehicles/{VIN}'
        scheduler = BlockingScheduler()
        self.vehicle_state = VehicleState(publisher, scheduler, account_prefix, vin_info)

    async def test_update_soc_with_no_bms_data(self):
        self.vehicle_state.update_data_conflicting_in_vehicle_and_bms(vehicle_status=get_mock_vehicle_status_resp(),
                                                                      charge_status=None)
        self.assert_mqtt_topic(TestVehicleState.get_topic(mqtt_topics.DRIVETRAIN_SOC), DRIVETRAIN_SOC_VEHICLE)
        self.assert_mqtt_topic(TestVehicleState.get_topic(mqtt_topics.DRIVETRAIN_RANGE), DRIVETRAIN_RANGE_VEHICLE)
        expected_topics = {
            '/vehicles/vin10000000000000/drivetrain/soc',
            '/vehicles/vin10000000000000/drivetrain/range',
        }
        self.assertSetEqual(expected_topics, set(self.vehicle_state.publisher.map.keys()))

    async def test_update_soc_with_bms_data(self):
        self.vehicle_state.update_data_conflicting_in_vehicle_and_bms(vehicle_status=get_mock_vehicle_status_resp(),
                                                                      charge_status=get_moc_charge_management_data_resp())
        self.assert_mqtt_topic(TestVehicleState.get_topic(mqtt_topics.DRIVETRAIN_SOC), DRIVETRAIN_SOC_BMS)
        self.assert_mqtt_topic(TestVehicleState.get_topic(mqtt_topics.DRIVETRAIN_RANGE), DRIVETRAIN_RANGE_BMS)
        expected_topics = {
            '/vehicles/vin10000000000000/drivetrain/soc',
            '/vehicles/vin10000000000000/drivetrain/range',
        }
        self.assertSetEqual(expected_topics, set(self.vehicle_state.publisher.map.keys()))

    def assert_mqtt_topic(self, topic: str, value):
        mqtt_map = self.vehicle_state.publisher.map
        if topic in mqtt_map:
            if isinstance(value, float) or isinstance(mqtt_map[topic], float):
                self.assertAlmostEqual(value, mqtt_map[topic], delta=1)
            else:
                self.assertEqual(value, mqtt_map[topic])
        else:
            self.fail(f'MQTT map does not contain topic {topic}')

    @staticmethod
    def get_topic(sub_topic: str) -> str:
        return f'/vehicles/{VIN}/{sub_topic}'
