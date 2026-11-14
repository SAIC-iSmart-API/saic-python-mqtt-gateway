from __future__ import annotations

import json

from apscheduler.schedulers.blocking import BlockingScheduler
from saic_ismart_client_ng.api.vehicle.schema import VinInfo

from configuration import Configuration
from integrations.home_assistant.discovery import HomeAssistantDiscovery
from integrations.home_assistant.gateway_discovery import (
    HomeAssistantGatewayDiscovery,
)
from tests.common_mocks import VIN
from tests.mocks import MessageCapturingConsolePublisher
from vehicle import RefreshMode, VehicleState
from vehicle_info import VehicleInfo

SAIC_USER = "User.Name@example.com"
LOCK_TOPIC = f"homeassistant/lock/{VIN}_mg/{VIN}_doors_lock/config"


def _publish_discovery(
    saic_user: str | None,
) -> MessageCapturingConsolePublisher:
    config = Configuration()
    config.anonymized_publishing = False
    config.ha_discovery_prefix = "homeassistant"
    config.saic_user = saic_user
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
    if saic_user is not None:
        HomeAssistantGatewayDiscovery(
            publisher=publisher,
            account_prefix=saic_user,
            discovery_prefix=config.ha_discovery_prefix,
        ).publish_ha_discovery_messages()
    return publisher


def _gateway_identifiers(publisher: MessageCapturingConsolePublisher) -> list[str]:
    gateway_payloads = [
        json.loads(payload)
        for topic, payload in publisher.map.items()
        if topic.startswith("homeassistant/") and "gateway_version" in topic
    ]
    assert len(gateway_payloads) == 1
    identifiers: list[str] = gateway_payloads[0]["device"]["identifiers"]
    return identifiers


def test_car_device_is_connected_via_the_gateway_device() -> None:
    publisher = _publish_discovery(SAIC_USER)

    device = json.loads(publisher.map[LOCK_TOPIC])["device"]
    assert device["via_device"] in _gateway_identifiers(publisher)


def test_no_via_device_without_saic_user() -> None:
    publisher = _publish_discovery(None)

    device = json.loads(publisher.map[LOCK_TOPIC])["device"]
    assert "via_device" not in device
