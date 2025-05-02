from __future__ import annotations

from dataclasses import asdict
import json
import logging

import mqtt_topics
from status_publisher import VehicleDataPublisher

LOG = logging.getLogger(__name__)


class VehicleInfoPublisher(VehicleDataPublisher):
    def publish(self) -> None:
        LOG.info("Publishing vehicle info to MQTT")
        self._transform_and_publish(
            topic=mqtt_topics.INTERNAL_CONFIGURATION_RAW,
            value=self._vehicle_info.configuration,
            transform=lambda c: json.dumps([asdict(x) for x in c]),
        )
        self._publish(
            topic=mqtt_topics.INFO_BRAND,
            value=self._vehicle_info.brand,
        )
        self._publish(
            topic=mqtt_topics.INFO_MODEL,
            value=self._vehicle_info.model,
        )
        self._publish(topic=mqtt_topics.INFO_YEAR, value=self._vehicle_info.model_year)
        self._publish(
            topic=mqtt_topics.INFO_SERIES,
            value=self._vehicle_info.series,
        )
        self._publish(
            topic=mqtt_topics.INFO_COLOR,
            value=self._vehicle_info.color,
        )
        for c in self._vehicle_info.configuration:
            property_value = c.itemValue
            if property_value is None:
                continue
            if property_name := c.itemName:
                property_name_topic = (
                    f"{mqtt_topics.INFO_CONFIGURATION}/{property_name}"
                )
                self._publish(
                    topic=property_name_topic,
                    value=property_value,
                )
            if property_code := c.itemCode:
                property_code_topic = (
                    f"{mqtt_topics.INFO_CONFIGURATION}/{property_code}"
                )
                self._publish(
                    topic=property_code_topic,
                    value=property_value,
                )
