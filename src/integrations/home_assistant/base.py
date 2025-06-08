from __future__ import annotations

import abc
from abc import abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from integrations.home_assistant.availability import HaCustomAvailabilityConfig


class HomeAssistantDiscoveryBase(metaclass=abc.ABCMeta):
    @abstractmethod
    def _get_state_topic(self, raw_topic: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def _get_command_topic(self, raw_topic: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def _publish_ha_discovery_message(
        self,
        sensor_type: str,
        sensor_name: str,
        payload: dict[str, Any],
        custom_availability: HaCustomAvailabilityConfig | None = None,
    ) -> str:
        raise NotImplementedError

    def _publish_select(
        self,
        topic: str,
        name: str,
        options: list[str],
        *,
        entity_category: str | None = None,
        enabled: bool = True,
        value_template: str = "{{ value }}",
        command_template: str = "{{ value }}",
        icon: str | None = None,
        custom_availability: HaCustomAvailabilityConfig | None = None,
    ) -> str:
        payload = {
            "state_topic": self._get_state_topic(topic),
            "command_topic": self._get_command_topic(topic),
            "value_template": value_template,
            "command_template": command_template,
            "options": options,
            "enabled_by_default": enabled,
        }
        if entity_category is not None:
            payload["entity_category"] = entity_category
        if icon is not None:
            payload["icon"] = icon

        return self._publish_ha_discovery_message(
            "select", name, payload, custom_availability
        )

    def _publish_text(
        self,
        topic: str,
        name: str,
        enabled: bool = True,
        icon: str | None = None,
        value_template: str = "{{ value }}",
        command_template: str = "{{ value }}",
        retain: bool = False,
        min_value: int | None = None,
        max_value: int | None = None,
        pattern: str | None = None,
        custom_availability: HaCustomAvailabilityConfig | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "state_topic": self._get_state_topic(topic),
            "command_topic": self._get_command_topic(topic),
            "value_template": value_template,
            "command_template": command_template,
            "retain": str(retain).lower(),
            "enabled_by_default": enabled,
        }
        if min_value is not None:
            payload["min"] = min_value
        if max_value is not None:
            payload["max"] = max_value
        if pattern is not None:
            payload["pattern"] = pattern
        if icon is not None:
            payload["icon"] = icon

        return self._publish_ha_discovery_message(
            "text", name, payload, custom_availability
        )

    def _publish_binary_sensor(
        self,
        topic: str,
        name: str,
        enabled: bool = True,
        device_class: str | None = None,
        value_template: str = "{{ value }}",
        payload_on: str = "True",
        payload_off: str = "False",
        icon: str | None = None,
        custom_availability: HaCustomAvailabilityConfig | None = None,
    ) -> str:
        payload = {
            "state_topic": self._get_state_topic(topic),
            "value_template": value_template,
            "payload_on": payload_on,
            "payload_off": payload_off,
            "enabled_by_default": enabled,
        }
        if device_class is not None:
            payload["device_class"] = device_class
        if icon is not None:
            payload["icon"] = icon

        return self._publish_ha_discovery_message(
            "binary_sensor", name, payload, custom_availability
        )

    def _publish_number(
        self,
        topic: str,
        name: str,
        enabled: bool = True,
        entity_category: str | None = None,
        device_class: str | None = None,
        state_class: str | None = None,
        unit_of_measurement: str | None = None,
        icon: str | None = None,
        value_template: str = "{{ value }}",
        retain: bool = False,
        mode: str = "auto",
        min_value: float = 1.0,
        max_value: float = 100.0,
        step: float = 1.0,
        custom_availability: HaCustomAvailabilityConfig | None = None,
    ) -> str:
        payload = {
            "state_topic": self._get_state_topic(topic),
            "command_topic": self._get_command_topic(topic),
            "value_template": value_template,
            "retain": str(retain).lower(),
            "mode": mode,
            "min": min_value,
            "max": max_value,
            "step": step,
            "enabled_by_default": enabled,
        }
        if entity_category is not None:
            payload["entity_category"] = entity_category
        if device_class is not None:
            payload["device_class"] = device_class
        if state_class is not None:
            payload["state_class"] = state_class
        if unit_of_measurement is not None:
            payload["unit_of_measurement"] = unit_of_measurement
        if icon is not None:
            payload["icon"] = icon

        return self._publish_ha_discovery_message(
            "number", name, payload, custom_availability
        )

    def _publish_switch(
        self,
        topic: str,
        name: str,
        *,
        enabled: bool = True,
        icon: str | None = None,
        value_template: str = "{{ value }}",
        payload_on: str = "True",
        payload_off: str = "False",
        custom_availability: HaCustomAvailabilityConfig | None = None,
    ) -> str:
        payload = {
            "state_topic": self._get_state_topic(topic),
            "command_topic": self._get_command_topic(topic),
            "value_template": value_template,
            "payload_on": payload_on,
            "payload_off": payload_off,
            "optimistic": False,
            "qos": 0,
            "enabled_by_default": enabled,
        }
        if icon is not None:
            payload["icon"] = icon
        return self._publish_ha_discovery_message(
            "switch", name, payload, custom_availability
        )

    def _publish_lock(
        self,
        topic: str,
        name: str,
        enabled: bool = True,
        icon: str | None = None,
        payload_lock: str = "True",
        payload_unlock: str = "False",
        state_locked: str = "True",
        state_unlocked: str = "False",
        custom_availability: HaCustomAvailabilityConfig | None = None,
    ) -> str:
        payload = {
            "state_topic": self._get_state_topic(topic),
            "command_topic": self._get_command_topic(topic),
            "payload_lock": payload_lock,
            "payload_unlock": payload_unlock,
            "state_locked": state_locked,
            "state_unlocked": state_unlocked,
            "optimistic": False,
            "qos": 0,
            "enabled_by_default": enabled,
        }
        if icon is not None:
            payload["icon"] = icon
        return self._publish_ha_discovery_message(
            "lock", name, payload, custom_availability
        )

    def _publish_sensor(
        self,
        topic: str,
        name: str,
        enabled: bool = True,
        entity_category: str | None = None,
        device_class: str | None = None,
        state_class: str | None = None,
        unit_of_measurement: str | None = None,
        icon: str | None = None,
        value_template: str = "{{ value }}",
        custom_availability: HaCustomAvailabilityConfig | None = None,
    ) -> str:
        payload = {
            "state_topic": self._get_state_topic(topic),
            "value_template": value_template,
            "enabled_by_default": enabled,
        }
        if entity_category is not None:
            payload["entity_category"] = entity_category
        if device_class is not None:
            payload["device_class"] = device_class
        if state_class is not None:
            payload["state_class"] = state_class
        if unit_of_measurement is not None:
            payload["unit_of_measurement"] = unit_of_measurement
        if icon is not None:
            payload["icon"] = icon

        return self._publish_ha_discovery_message(
            "sensor", name, payload, custom_availability
        )
