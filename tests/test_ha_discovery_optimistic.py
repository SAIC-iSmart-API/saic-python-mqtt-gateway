from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, override
import unittest

from configuration import Configuration
from integrations.home_assistant.base import HomeAssistantDiscoveryBase

from .common_mocks import VIN
from .mocks import MessageCapturingConsolePublisher

if TYPE_CHECKING:
    from integrations.home_assistant.availability import HaCustomAvailabilityConfig


class _Discovery(HomeAssistantDiscoveryBase):
    """Minimal concrete subclass to exercise the protected publish helpers.

    Used to build HA MQTT discovery payloads for writable entities.
    """

    def __init__(self, publisher: MessageCapturingConsolePublisher) -> None:
        self.publisher = publisher

    @override
    def _get_state_topic(self, raw_topic: str) -> str:
        return f"vehicles/{VIN}/{raw_topic}"

    @override
    def _get_command_topic(self, raw_topic: str) -> str:
        return f"vehicles/{VIN}/{raw_topic}/set"

    @override
    def _publish_ha_discovery_message(
        self,
        sensor_type: str,
        sensor_name: str,
        payload: dict[str, Any],
        custom_availability: HaCustomAvailabilityConfig | None = None,
    ) -> str:
        topic = f"homeassistant/{sensor_type}/{VIN}/{sensor_name}/config"
        self.publisher.publish_json(topic, payload, no_prefix=True)
        return topic

    def _decode(self, topic: str) -> dict[str, Any]:
        decoded: dict[str, Any] = json.loads(self.publisher.map[topic])
        return decoded

    def number_payload(self) -> dict[str, Any]:
        topic = self._publish_number(topic="drivetrain/socTarget", name="target_soc")
        return self._decode(topic)

    def select_payload(self) -> dict[str, Any]:
        topic = self._publish_select(
            topic="drivetrain/chargeCurrentLimit",
            name="charge_current_limit",
            options=["MAX", "6A"],
        )
        return self._decode(topic)

    def text_payload(self) -> dict[str, Any]:
        topic = self._publish_text(
            topic="drivetrain/scheduledChargingStart", name="schedule"
        )
        return self._decode(topic)

    def switch_payload(self) -> dict[str, Any]:
        topic = self._publish_switch(topic="drivetrain/charging", name="charging")
        return self._decode(topic)


class TestWritableEntitiesAreNonOptimistic(unittest.TestCase):
    """Writable entities must declare `optimistic: false`.

    HA reads state from `state_topic` rather than republishing its own cached
    value on restart. Guards #375 (target SoC reset on restart) and the
    analogous battery-capacity report.
    """

    def setUp(self) -> None:
        publisher = MessageCapturingConsolePublisher(Configuration())
        self.discovery = _Discovery(publisher)

    def test_number_payload_sets_optimistic_false(self) -> None:
        assert self.discovery.number_payload().get("optimistic") is False

    def test_select_payload_sets_optimistic_false(self) -> None:
        assert self.discovery.select_payload().get("optimistic") is False

    def test_text_payload_sets_optimistic_false(self) -> None:
        assert self.discovery.text_payload().get("optimistic") is False

    def test_switch_payload_keeps_optimistic_false(self) -> None:
        # Regression guard: switches were already correct; ensure the audit
        # didn't accidentally remove the flag.
        assert self.discovery.switch_payload().get("optimistic") is False
