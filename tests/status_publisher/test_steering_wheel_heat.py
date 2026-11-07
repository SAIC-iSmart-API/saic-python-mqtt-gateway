from __future__ import annotations

import unittest

from saic_ismart_client_ng.api.vehicle import BasicVehicleStatus
from saic_ismart_client_ng.api.vehicle.schema import VinInfo

from configuration import Configuration
import mqtt_topics
from status_publisher.vehicle.basic_vehicle_status import BasicVehicleStatusPublisher
from tests.common_mocks import VIN
from tests.mocks import MessageCapturingConsolePublisher
from vehicle_info import VehicleInfo

VEHICLE_PREFIX = f"vehicles/{VIN}"
STATE_TOPIC = f"{VEHICLE_PREFIX}/{mqtt_topics.CLIMATE_STEERING_WHEEL_HEAT}"


class TestSteeringWheelHeatStatus(unittest.TestCase):
    def setUp(self) -> None:
        config = Configuration()
        config.anonymized_publishing = False
        self.capturing = MessageCapturingConsolePublisher(config)
        vin_info = VinInfo()
        vin_info.vin = VIN
        self.publisher = BasicVehicleStatusPublisher(
            VehicleInfo(vin_info, None), self.capturing, VEHICLE_PREFIX
        )

    def test_reports_heating_on(self) -> None:
        self.publisher.publish(BasicVehicleStatus(steeringHeatLevel=1))

        assert self.capturing.map[STATE_TOPIC] == "on"

    def test_reports_heating_off(self) -> None:
        self.publisher.publish(BasicVehicleStatus(steeringHeatLevel=0))

        assert self.capturing.map[STATE_TOPIC] == "off"

    def test_reports_heating_on_for_levels_above_one(self) -> None:
        # The car reports 3 while the heater is on
        self.publisher.publish(BasicVehicleStatus(steeringHeatLevel=3))

        assert self.capturing.map[STATE_TOPIC] == "on"

    def test_missing_status_is_not_published(self) -> None:
        self.publisher.publish(BasicVehicleStatus())

        assert STATE_TOPIC not in self.capturing.map

    def test_unknown_status_preserves_previous_state(self) -> None:
        self.publisher.publish(BasicVehicleStatus(steeringHeatLevel=1))

        for level in (None, -1):
            with self.subTest(level=level):
                self.publisher.publish(BasicVehicleStatus(steeringHeatLevel=level))

                assert self.capturing.map[STATE_TOPIC] == "on"
                assert self.capturing.publish_count[STATE_TOPIC] == 1
