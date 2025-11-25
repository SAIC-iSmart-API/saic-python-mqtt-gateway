from __future__ import annotations

import logging
from typing import Any, override

from publisher.core import Publisher

LOG = logging.getLogger(__name__)
LOG.setLevel(level="DEBUG")


class ConsolePublisher(Publisher):
    @override
    async def connect(self) -> None:
        pass

    @override
    def is_connected(self) -> bool:
        return True

    @override
    def enable_commands(self) -> None:
        pass

    @override
    def publish_json(
        self,
        key: str,
        data: dict[str, Any],
        no_prefix: bool = False,
        retain: bool = False,
        qos: int = 0,
    ) -> None:
        anonymized_json = self.dict_to_anonymized_json(data)
        self.internal_publish(key, anonymized_json)

    @override
    def publish_str(
        self,
        key: str,
        value: str,
        no_prefix: bool = False,
        retain: bool = False,
        qos: int = 0,
    ) -> None:
        self.internal_publish(key, value)

    @override
    def publish_int(
        self,
        key: str,
        value: int,
        no_prefix: bool = False,
        retain: bool = False,
        qos: int = 0,
    ) -> None:
        self.internal_publish(key, value)

    @override
    def publish_bool(
        self,
        key: str,
        value: bool,
        no_prefix: bool = False,
        retain: bool = False,
        qos: int = 0,
    ) -> None:
        self.internal_publish(key, value)

    @override
    def publish_float(
        self,
        key: str,
        value: float,
        no_prefix: bool = False,
        retain: bool = False,
        qos: int = 0,
    ) -> None:
        self.internal_publish(key, value)

    @override
    def clear_topic(self, key: str, no_prefix: bool = False, qos: int = 0) -> None:
        self.internal_publish(key, None)

    def internal_publish(self, key: str, value: Any) -> None:
        LOG.debug(f"{key}: {value}")
