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
import mqtt_topics
from tests.common_mocks import VIN
from tests.mocks import MessageCapturingConsolePublisher
from vehicle import RefreshMode, VehicleState
from vehicle_info import VehicleInfo

# Six entities whose `/set` commands HA must retain so the user's last value
# survives a gateway restart. Stored as the path suffix of the entity's state
# topic so we can match against published HA discovery payloads.
RETAINED_ENTITY_TOPICS = {
    mqtt_topics.REFRESH_MODE,
    mqtt_topics.REFRESH_PERIOD_ACTIVE,
    mqtt_topics.REFRESH_PERIOD_INACTIVE,
    mqtt_topics.REFRESH_PERIOD_AFTER_SHUTDOWN,
    mqtt_topics.REFRESH_PERIOD_INACTIVE_GRACE,
    mqtt_topics.DRIVETRAIN_TOTAL_BATTERY_CAPACITY,
}

# Sample of writable entities that must NOT be retained. SOC target / charge
# current are API-backed; charging is action-bearing.
NON_RETAINED_ENTITY_TOPICS = {
    mqtt_topics.DRIVETRAIN_SOC_TARGET,
    mqtt_topics.DRIVETRAIN_CHARGECURRENT_LIMIT,
}


def _make_discovery() -> tuple[
    HomeAssistantDiscovery, MessageCapturingConsolePublisher
]:
    config = Configuration()
    config.anonymized_publishing = False
    config.ha_discovery_prefix = "homeassistant"
    publisher = MessageCapturingConsolePublisher(config)
    vin_info = VinInfo()
    vin_info.vin = VIN
    vin_info.series = "EH32 S"
    vin_info.modelName = "MG4 Electric"
    vin_info.modelYear = "2022"
    vin_info.vehicleModelConfiguration = [
        VehicleModelConfiguration("BATTERY", "BATTERY", "1"),
        VehicleModelConfiguration("BType", "Battery", "1"),
    ]
    vehicle_info = VehicleInfo(vin_info, None)
    account_prefix = f"/vehicles/{VIN}"
    scheduler = BlockingScheduler()
    vehicle_state = VehicleState(publisher, scheduler, account_prefix, vehicle_info)
    vehicle_state.refresh_period_active = 30
    vehicle_state.refresh_period_inactive = 120
    vehicle_state.refresh_period_after_shutdown = 60
    vehicle_state.refresh_period_inactive_grace = 600
    vehicle_state.refresh_mode = RefreshMode.PERIODIC
    discovery = HomeAssistantDiscovery(vehicle_state, vehicle_info, config)
    return discovery, publisher


def _writable_payloads(
    publisher: MessageCapturingConsolePublisher,
) -> list[dict[str, object]]:
    """Return every published discovery payload that has a `command_topic`."""
    payloads: list[dict[str, object]] = []
    for raw in publisher.map.values():
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and "command_topic" in payload:
            payloads.append(payload)
    return payloads


def _payload_for_state_topic_suffix(
    payloads: list[dict[str, object]], suffix: str
) -> dict[str, object] | None:
    for payload in payloads:
        state_topic = payload.get("state_topic")
        if isinstance(state_topic, str) and state_topic.endswith(f"/{suffix}"):
            return payload
    return None


class TestDiscoveryRetainFlag(unittest.TestCase):
    """The six idempotent persistence-relevant entities must be retained."""

    def test_required_entities_have_retain_true(self) -> None:
        discovery, publisher = _make_discovery()
        discovery.publish_ha_discovery_messages()
        payloads = _writable_payloads(publisher)

        for topic in RETAINED_ENTITY_TOPICS:
            payload = _payload_for_state_topic_suffix(payloads, topic)
            assert payload is not None, (
                f"No writable HA discovery payload found for topic {topic}"
            )
            assert payload.get("retain") == "true", (
                f"Expected retain=true for {topic}, got {payload.get('retain')!r}"
            )

    def test_non_retained_entities_keep_retain_false(self) -> None:
        discovery, publisher = _make_discovery()
        discovery.publish_ha_discovery_messages()
        payloads = _writable_payloads(publisher)

        for topic in NON_RETAINED_ENTITY_TOPICS:
            payload = _payload_for_state_topic_suffix(payloads, topic)
            if payload is None:
                continue  # entity not published for this vehicle config
            assert payload.get("retain") in ("false", None), (
                f"Expected retain!=true for {topic}, got {payload.get('retain')!r}"
            )
