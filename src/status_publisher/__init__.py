from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Final, TypeVar

from utils import datetime_to_str

if TYPE_CHECKING:
    from collections.abc import Callable

    from publisher.core import Publisher
    from vehicle_info import VehicleInfo

T = TypeVar("T")
Publishable = TypeVar("Publishable", str, int, float, bool, dict[str, Any], datetime)


class VehicleDataPublisher:
    def __init__(
        self, vin: VehicleInfo, publisher: Publisher, mqtt_vehicle_prefix: str
    ) -> None:
        self._vehicle_info: Final[VehicleInfo] = vin
        self.__publisher: Final[Publisher] = publisher
        self.__mqtt_vehicle_prefix: Final[str] = mqtt_vehicle_prefix

    def _publish(
        self,
        *,
        topic: str,
        value: Publishable | None,
        validator: Callable[[Publishable], bool] = lambda _: True,
        no_prefix: bool = False,
    ) -> tuple[bool, Publishable | None]:
        if value is None or not validator(value):
            return False, None
        actual_topic = topic if no_prefix else self.__get_topic(topic)
        published = self._publish_directly(topic=actual_topic, value=value)
        return published, value

    def _transform_and_publish(
        self,
        *,
        topic: str,
        value: T | None,
        validator: Callable[[T], bool] = lambda _: True,
        transform: Callable[[T], Publishable],
        no_prefix: bool = False,
    ) -> tuple[bool, Publishable | None]:
        if value is None or not validator(value):
            return False, None
        actual_topic = topic if no_prefix else self.__get_topic(topic)
        transformed_value = transform(value)
        published = self._publish_directly(topic=actual_topic, value=transformed_value)
        return published, transformed_value

    def _publish_directly(self, *, topic: str, value: Publishable) -> bool:
        published = False
        if isinstance(value, bool):
            self.__publisher.publish_bool(topic, value)
            published = True
        elif isinstance(value, int):
            self.__publisher.publish_int(topic, value)
            published = True
        elif isinstance(value, float):
            self.__publisher.publish_float(topic, value)
            published = True
        elif isinstance(value, str):
            self.__publisher.publish_str(topic, value)
            published = True
        elif isinstance(value, dict):
            self.__publisher.publish_json(topic, value)
            published = True
        elif isinstance(value, datetime):
            self.__publisher.publish_str(topic, datetime_to_str(value))
            published = True
        return published

    def __get_topic(self, sub_topic: str) -> str:
        return f"{self.__mqtt_vehicle_prefix}/{sub_topic}"
