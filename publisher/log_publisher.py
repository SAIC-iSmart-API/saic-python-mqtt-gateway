import logging
from typing import override

from configuration import Configuration
from publisher.core import Publisher

LOG = logging.getLogger(__name__)
LOG.setLevel(level="DEBUG")


class Logger(Publisher):
    def __init__(self, configuration: Configuration):
        super().__init__(configuration)
        self.map = {}

    @override
    def is_connected(self) -> bool:
        return True

    @override
    def publish_json(self, key: str, data: dict, no_prefix: bool = False) -> None:
        anonymized_json = self.dict_to_anonymized_json(data)
        self.__internal_publish(key, anonymized_json)

    @override
    def publish_str(self, key: str, value: str, no_prefix: bool = False) -> None:
        self.__internal_publish(key, value)

    @override
    def publish_int(self, key: str, value: int, no_prefix: bool = False) -> None:
        self.__internal_publish(key, value)

    @override
    def publish_bool(self, key: str, value: bool, no_prefix: bool = False) -> None:
        if value is None:
            value = False
        elif isinstance(value, int):
            value = value == 1
        self.__internal_publish(key, value)

    @override
    def publish_float(self, key: str, value: float, no_prefix: bool = False) -> None:
        self.__internal_publish(key, value)

    def __internal_publish(self, key, value):
        self.map[key] = value
        LOG.debug(f'{key}: {value}')
