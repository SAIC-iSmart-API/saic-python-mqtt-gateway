from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, override

from integrations.home_assistant.availability import (
    HaCustomAvailabilityConfig,
    HaCustomAvailabilityEntry,
)
from integrations.home_assistant.base import (
    _GATEWAY_VERSION,
    _ORIGIN,
    HomeAssistantDiscoveryBase,
)
from integrations.home_assistant.utils import gateway_device_id, snake_case
import mqtt_topics
from publisher.mqtt_publisher import MqttPublisher

if TYPE_CHECKING:
    from publisher.core import Publisher

LOG = logging.getLogger(__name__)


class HomeAssistantGatewayDiscovery(HomeAssistantDiscoveryBase):
    def __init__(
        self,
        publisher: Publisher,
        account_prefix: str,
        discovery_prefix: str,
    ) -> None:
        self.__publisher = publisher
        self.__account_prefix = account_prefix
        self.__discovery_prefix = discovery_prefix
        self.__system_availability_config = HaCustomAvailabilityConfig(
            rules=[
                HaCustomAvailabilityEntry(
                    topic=self.__get_full_topic(mqtt_topics.INTERNAL_LWT)
                )
            ]
        )
        self.published = False

    def publish_ha_discovery_messages(self) -> None:
        LOG.debug("Publishing Home Assistant gateway discovery messages")
        self.__publish_gateway_sensors()
        self.published = True

    def reset(self) -> None:
        self.published = False

    def __publish_gateway_sensors(self) -> None:
        self._publish_sensor(
            mqtt_topics.ACCOUNT_GATEWAY_VERSION,
            "Gateway version",
            entity_category="diagnostic",
            icon="mdi:tag",
            custom_availability=self.__system_availability_config,
        )
        self._publish_sensor(
            mqtt_topics.ACCOUNT_USER_TIMEZONE,
            "Account timezone",
            entity_category="diagnostic",
            icon="mdi:map-clock",
            custom_availability=self.__system_availability_config,
        )
        self._publish_sensor(
            mqtt_topics.ACCOUNT_REFRESH_INTERVAL,
            "Account refresh interval",
            entity_category="diagnostic",
            unit_of_measurement="s",
            icon="mdi:timer-sync",
            custom_availability=self.__system_availability_config,
        )
        self._publish_sensor(
            mqtt_topics.ACCOUNT_LAST_REFRESH,
            "Account last refresh",
            device_class="timestamp",
            entity_category="diagnostic",
            custom_availability=self.__system_availability_config,
        )
        self._publish_sensor(
            mqtt_topics.ACCOUNT_LAST_LOGIN,
            "Account last login",
            device_class="timestamp",
            entity_category="diagnostic",
            custom_availability=self.__system_availability_config,
        )
        self._publish_sensor(
            mqtt_topics.ACCOUNT_LAST_LOGIN_ERROR,
            "Account last login error",
            device_class="timestamp",
            entity_category="diagnostic",
            custom_availability=self.__system_availability_config,
        )

    @override
    def _get_state_topic(self, raw_topic: str) -> str:
        return self.__get_full_topic(f"{self.__account_prefix}/{raw_topic}")

    @override
    def _get_command_topic(self, raw_topic: str) -> str:
        return self.__get_full_topic(
            f"{self.__account_prefix}/{raw_topic}/{mqtt_topics.SET_SUFFIX}"
        )

    def __get_full_topic(self, topic: str) -> str:
        if isinstance(self.__publisher, MqttPublisher):
            return self.__publisher.get_topic(topic, no_prefix=False)
        return topic

    @property
    def __gateway_id(self) -> str:
        return gateway_device_id(self.__account_prefix)

    def __get_device_node(self) -> dict[str, Any]:
        return {
            "name": "SAIC Python MQTT Gateway",
            "manufacturer": "SAIC",
            "model": "Python MQTT Gateway",
            "sw_version": _GATEWAY_VERSION,
            "identifiers": [self.__gateway_id],
        }

    def __get_common_attributes(
        self,
        unique_id: str,
        domain: str,
        name: str,
        custom_availability: HaCustomAvailabilityConfig | None = None,
    ) -> dict[str, Any]:
        common_attributes = {
            "name": name,
            "device": self.__get_device_node(),
            "o": _ORIGIN,
            "unique_id": unique_id,
            "default_entity_id": f"{domain}.{unique_id}",
        }

        if custom_availability is not None:
            common_attributes.update(custom_availability.to_dict())
        else:
            common_attributes.update(self.__system_availability_config.to_dict())

        return common_attributes

    @override
    def _publish_ha_discovery_message(
        self,
        sensor_type: str,
        sensor_name: str,
        payload: dict[str, Any],
        custom_availability: HaCustomAvailabilityConfig | None = None,
    ) -> str:
        gateway_id = self.__gateway_id
        unique_id = f"{gateway_id}_{snake_case(sensor_name)}"
        final_payload = (
            self.__get_common_attributes(
                unique_id, sensor_type, sensor_name, custom_availability
            )
            | payload
        )
        ha_topic = f"{self.__discovery_prefix}/{sensor_type}/{gateway_id}_gw/{unique_id}/config"
        self.__publisher.publish_json(ha_topic, final_payload, no_prefix=True)
        return f"{sensor_type}.{unique_id}"
