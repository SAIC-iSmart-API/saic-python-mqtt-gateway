from __future__ import annotations

import json

from apscheduler.schedulers.blocking import BlockingScheduler
from saic_ismart_client_ng.api.vehicle.schema import VinInfo

from configuration import Configuration
from integrations.home_assistant.discovery import HomeAssistantDiscovery
from tests.common_mocks import VIN
from tests.mocks import MessageCapturingConsolePublisher
from vehicle import RefreshMode, VehicleState
from vehicle_info import VehicleInfo

COVER_TOPIC = f"homeassistant/cover/{VIN}_mg/{VIN}_power_tailgate/config"


def _publish_discovery() -> MessageCapturingConsolePublisher:
    config = Configuration()
    config.anonymized_publishing = False
    config.ha_discovery_prefix = "homeassistant"
    publisher = MessageCapturingConsolePublisher(config)
    vin_info = VinInfo()
    vin_info.vin = VIN
    vin_info.series = "EH32 S"
    vin_info.modelName = "MG4 Electric"
    vin_info.modelYear = "2022"
    vehicle_info = VehicleInfo(vin_info, None)
    vehicle_state = VehicleState(
        publisher, BlockingScheduler(), f"/vehicles/{VIN}", vehicle_info
    )
    vehicle_state.refresh_period_active = 30
    vehicle_state.refresh_period_inactive = 120
    vehicle_state.refresh_period_after_shutdown = 60
    vehicle_state.refresh_period_inactive_grace = 600
    vehicle_state.refresh_mode = RefreshMode.PERIODIC
    HomeAssistantDiscovery(
        vehicle_state, vehicle_info, config
    ).publish_ha_discovery_messages()
    return publisher


def test_power_tailgate_cover_published_for_every_car() -> None:
    publisher = _publish_discovery()

    assert COVER_TOPIC in publisher.map
    payload = json.loads(publisher.map[COVER_TOPIC])
    assert payload["device_class"] == "door"
    assert payload["state_topic"] == f"/vehicles/{VIN}/doors/boot"
    assert payload["command_topic"] == f"/vehicles/{VIN}/doors/boot/powerTailgate/set"
    assert payload["payload_open"] == "open"
    assert payload["payload_close"] == "close"
    assert payload["payload_stop"] is None
    assert payload["state_open"] == "True"
    assert payload["state_closed"] == "False"
    assert payload["optimistic"] is False
    assert payload["enabled_by_default"] is False


def test_boot_lock_unchanged() -> None:
    publisher = _publish_discovery()

    lock_topic = f"homeassistant/lock/{VIN}_mg/{VIN}_boot_lock/config"
    payload = json.loads(publisher.map[lock_topic])
    assert payload["command_topic"] == f"/vehicles/{VIN}/doors/boot/set"
