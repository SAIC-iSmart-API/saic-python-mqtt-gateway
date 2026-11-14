from __future__ import annotations

import json

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


def _publish_discovery(codes: dict[str, str], series: str = "EH32 S") -> dict[str, str]:
    config = Configuration()
    config.anonymized_publishing = False
    config.ha_discovery_prefix = "homeassistant"
    publisher = MessageCapturingConsolePublisher(config)
    vin_info = VinInfo()
    vin_info.vin = VIN
    vin_info.series = series
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


def _enabled(published: dict[str, str], component: str, name: str) -> bool:
    payload = published[_topic(component, name)]
    assert payload != ""
    enabled: bool = json.loads(payload)["enabled_by_default"]
    return enabled


@pytest.mark.parametrize(("component", "name"), GATED_ENTITIES)
def test_entity_published_when_supported(component: str, name: str) -> None:
    published = _publish_discovery(ALL_FEATURES)
    assert _enabled(published, component, name)


@pytest.mark.parametrize(("component", "name"), GATED_ENTITIES)
def test_entity_published_when_code_absent(component: str, name: str) -> None:
    published = _publish_discovery({})
    assert _enabled(published, component, name)


@pytest.mark.parametrize(("component", "name"), GATED_ENTITIES)
def test_entity_disabled_by_default_when_code_disabled(
    component: str, name: str
) -> None:
    published = _publish_discovery(
        {"DOOR": "0000", "BOOT": "0", "J17": "0", "INTEMP": "0"}
    )
    assert not _enabled(published, component, name)


@pytest.mark.parametrize(("component", "name"), UNGATED_ENTITIES)
def test_entity_published_even_when_code_disabled(component: str, name: str) -> None:
    published = _publish_discovery(
        {"WINDOW": "0000", "BONNUT": "0", "BATTERY": "0", "EXTEMP": "0"}
    )
    assert published[_topic(component, name)] != ""


def test_door_mask_gates_single_entities() -> None:
    published = _publish_discovery({"DOOR": "1100"})
    assert _enabled(published, "binary_sensor", "door_driver")
    assert _enabled(published, "binary_sensor", "door_passenger")
    assert not _enabled(published, "binary_sensor", "door_rear_left")
    assert not _enabled(published, "binary_sensor", "door_rear_right")


def _soc_enabled(series: str) -> bool:
    published = _publish_discovery({}, series=series)
    payload = json.loads(published[_topic("sensor", "soc")])
    enabled: bool = payload["enabled_by_default"]
    return enabled


@pytest.mark.parametrize("series", ["ZP22 EU", "ZS32 EU"])
def test_battery_entities_disabled_by_default_on_hybrids(series: str) -> None:
    assert not _soc_enabled(series)


def test_battery_entities_enabled_on_ev() -> None:
    assert _soc_enabled("EH32 S")
