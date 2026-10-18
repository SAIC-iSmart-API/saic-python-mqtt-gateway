from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler
import pytest
from saic_ismart_client_ng.api.vehicle.schema import (
    VehicleModelConfiguration,
    VinInfo,
)

from configuration import Configuration
from integrations.home_assistant.discovery import HomeAssistantDiscovery
from vehicle import RefreshMode, VehicleState
from vehicle_info import VehicleInfo

from .common_mocks import VIN
from .mocks import MessageCapturingConsolePublisher

ALL_FEATURES = {
    "DOOR": "1111",
    "BOOT": "1",
    "J17": "1",
    "INTEMP": "1",
}

GATED_ENTITIES = [
    ("binary_sensor", "door_driver"),
    ("binary_sensor", "door_passenger"),
    ("binary_sensor", "door_rear_left"),
    ("binary_sensor", "door_rear_right"),
    ("binary_sensor", "boot"),
    ("sensor", "tyres_front_left_pressure"),
    ("sensor", "tyres_front_right_pressure"),
    ("sensor", "tyres_rear_left_pressure"),
    ("sensor", "tyres_rear_right_pressure"),
    ("sensor", "interior_temperature"),
]

# Codes that real vehicles report as 0 while still sending the data
UNGATED_ENTITIES = [
    ("binary_sensor", "window_driver"),
    ("binary_sensor", "window_passenger"),
    ("binary_sensor", "window_rear_left"),
    ("binary_sensor", "window_rear_right"),
    ("binary_sensor", "bonnet"),
    ("sensor", "auxiliary_battery_voltage"),
    ("sensor", "exterior_temperature"),
]


def _publish_discovery(codes: dict[str, str]) -> dict[str, str]:
    config = Configuration()
    config.anonymized_publishing = False
    config.ha_discovery_prefix = "homeassistant"
    publisher = MessageCapturingConsolePublisher(config)
    vin_info = VinInfo()
    vin_info.vin = VIN
    vin_info.series = "EH32 S"
    vin_info.vehicleModelConfiguration = [
        VehicleModelConfiguration(itemCode=code, itemName=code, itemValue=value)
        for code, value in codes.items()
    ]
    vehicle_info = VehicleInfo(vin_info, None)
    vehicle_state = VehicleState(
        publisher, BlockingScheduler(), f"/vehicles/{VIN}", vehicle_info
    )
    vehicle_state.refresh_period_active = 30
    vehicle_state.refresh_period_inactive = 120
    vehicle_state.refresh_period_after_shutdown = 60
    vehicle_state.refresh_period_inactive_grace = 600
    vehicle_state.refresh_mode = RefreshMode.PERIODIC
    discovery = HomeAssistantDiscovery(vehicle_state, vehicle_info, config)
    assert discovery.publish_ha_discovery_messages()
    return publisher.map


def _topic(component: str, name: str) -> str:
    return f"homeassistant/{component}/{VIN}_mg/{VIN}_{name}/config"


@pytest.mark.parametrize(("component", "name"), GATED_ENTITIES)
def test_entity_published_when_supported(component: str, name: str) -> None:
    published = _publish_discovery(ALL_FEATURES)
    assert published[_topic(component, name)] != ""


@pytest.mark.parametrize(("component", "name"), GATED_ENTITIES)
def test_entity_unpublished_when_code_absent(component: str, name: str) -> None:
    published = _publish_discovery({})
    assert published[_topic(component, name)] == ""


@pytest.mark.parametrize(("component", "name"), UNGATED_ENTITIES)
def test_entity_published_even_when_code_disabled(component: str, name: str) -> None:
    published = _publish_discovery(
        {"WINDOW": "0000", "BONNUT": "0", "BATTERY": "0", "EXTEMP": "0"}
    )
    assert published[_topic(component, name)] != ""


def test_door_mask_gates_single_entities() -> None:
    published = _publish_discovery({"DOOR": "1100"})
    assert published[_topic("binary_sensor", "door_driver")] != ""
    assert published[_topic("binary_sensor", "door_passenger")] != ""
    assert published[_topic("binary_sensor", "door_rear_left")] == ""
    assert published[_topic("binary_sensor", "door_rear_right")] == ""
