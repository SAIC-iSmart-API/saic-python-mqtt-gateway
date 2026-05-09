from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Final

from publisher.core import Publishable

if TYPE_CHECKING:
    from collections.abc import Callable

    from publisher.core import Publisher
    from vehicle_info import VehicleInfo


class VehicleDataPublisher[I, O](metaclass=ABCMeta):
    def __init__(
        self, vin: VehicleInfo, publisher: Publisher, mqtt_vehicle_prefix: str
    ) -> None:
        self._vehicle_info: Final[VehicleInfo] = vin
        self.__publisher: Final[Publisher] = publisher
        self.__mqtt_vehicle_prefix: Final[str] = mqtt_vehicle_prefix

    @abstractmethod
    def publish(self, data: I) -> O:
        raise NotImplementedError

    def _publish[V: Publishable](
        self,
        *,
        topic: str,
        value: V | None,
        validator: Callable[[V], bool] = lambda _: True,
        no_prefix: bool = False,
        retain: bool = True,
    ) -> tuple[bool, V | None]:
        if value is None or not validator(value):
            return False, None
        actual_topic = topic if no_prefix else self.__get_topic(topic)
        self.__publisher.publish(actual_topic, value, retain=retain)
        return True, value

    def _transform_and_publish[T, V: Publishable](
        self,
        *,
        topic: str,
        value: T | None,
        validator: Callable[[T], bool] = lambda _: True,
        transform: Callable[[T], V],
        no_prefix: bool = False,
        retain: bool = True,
    ) -> tuple[bool, V | None]:
        if value is None or not validator(value):
            return False, None
        actual_topic = topic if no_prefix else self.__get_topic(topic)
        transformed_value = transform(value)
        self.__publisher.publish(actual_topic, transformed_value, retain=retain)
        return True, transformed_value

    def __get_topic(self, sub_topic: str) -> str:
        return f"{self.__mqtt_vehicle_prefix}/{sub_topic}"
