from __future__ import annotations

import json
import unittest

from apscheduler.schedulers.blocking import BlockingScheduler
from saic_ismart_client_ng.api.vehicle.schema import (
    VehicleModelConfiguration,
    VinInfo,
)

from configuration import Configuration
from integrations.home_assistant.discovery import HomeAssistantDiscovery
from vehicle import VehicleState
from vehicle_info import VehicleInfo

from .common_mocks import VIN
from .mocks import MessageCapturingConsolePublisher


class TestHaDiscoveryWindows(unittest.TestCase):
    """Test that window entities are published as binary_sensors, not switches."""

    def _make_discovery(
        self, *, has_sunroof: bool = False
    ) -> tuple[HomeAssistantDiscovery, MessageCapturingConsolePublisher]:
        config = Configuration()
        config.anonymized_publishing = False
        config.ha_discovery_prefix = "homeassistant"
        publisher = MessageCapturingConsolePublisher(config)
        vin_info = VinInfo()
        vin_info.vin = VIN
        vin_info.series = "EH32 S"
        vin_info.modelName = "MG4 Electric"
        vin_info.modelYear = "2022"
        configs = [
            VehicleModelConfiguration("BATTERY", "BATTERY", "1"),
            VehicleModelConfiguration("BType", "Battery", "1"),
            VehicleModelConfiguration(
                "S35", "Sunroof", "1" if has_sunroof else "0"
            ),
        ]
        vin_info.vehicleModelConfiguration = configs
        vehicle_info = VehicleInfo(vin_info, None)
        account_prefix = f"/vehicles/{VIN}"
        scheduler = BlockingScheduler()
        vehicle_state = VehicleState(publisher, scheduler, account_prefix, vehicle_info)
        # Make vehicle state complete so discovery publishes
        vehicle_state.refresh_period_active = 30
        vehicle_state.refresh_period_inactive = 120
        vehicle_state.refresh_period_after_shutdown = 60
        vehicle_state.refresh_period_inactive_grace = 600
        vehicle_state.refresh_mode = "periodic"
        discovery = HomeAssistantDiscovery(vehicle_state, vehicle_info, config)
        return discovery, publisher

    def _discovery_topics(self, publisher: MessageCapturingConsolePublisher) -> set[str]:
        return set(publisher.map.keys())

    def test_windows_published_as_binary_sensors(self) -> None:
        discovery, publisher = self._make_discovery()
        discovery.publish_ha_discovery_messages()

        topics = self._discovery_topics(publisher)
        window_names = [
            "window_driver",
            "window_passenger",
            "window_rear_left",
            "window_rear_right",
        ]
        for name in window_names:
            binary_sensor_topic = (
                f"homeassistant/binary_sensor/{VIN}_mg/{VIN}_{name}/config"
            )
            assert binary_sensor_topic in topics, (
                f"Expected binary_sensor discovery for {name}"
            )
            # Verify the payload has no command_topic (read-only)
            payload = json.loads(publisher.map[binary_sensor_topic])
            assert "command_topic" not in payload
            assert payload["device_class"] == "window"

    def test_windows_not_published_as_switches(self) -> None:
        discovery, publisher = self._make_discovery()
        discovery.publish_ha_discovery_messages()

        topics = self._discovery_topics(publisher)
        window_names = [
            "window_driver",
            "window_passenger",
            "window_rear_left",
            "window_rear_right",
        ]
        for name in window_names:
            switch_topic = f"homeassistant/switch/{VIN}_mg/{VIN}_{name}/config"
            if switch_topic in topics:
                # Should be an empty unpublish message
                assert publisher.map[switch_topic] == "", (
                    f"Switch for {name} should be unpublished (empty payload)"
                )

    def test_sunroof_published_as_binary_sensor_when_supported(self) -> None:
        discovery, publisher = self._make_discovery(has_sunroof=True)
        discovery.publish_ha_discovery_messages()

        topics = self._discovery_topics(publisher)
        sunroof_topic = (
            f"homeassistant/binary_sensor/{VIN}_mg/{VIN}_sun_roof/config"
        )
        assert sunroof_topic in topics

    def test_sunroof_unpublished_when_not_supported(self) -> None:
        discovery, publisher = self._make_discovery(has_sunroof=False)
        discovery.publish_ha_discovery_messages()

        topics = self._discovery_topics(publisher)
        sunroof_binary = (
            f"homeassistant/binary_sensor/{VIN}_mg/{VIN}_sun_roof/config"
        )
        if sunroof_binary in topics:
            assert publisher.map[sunroof_binary] == ""
