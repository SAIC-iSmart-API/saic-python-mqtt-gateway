from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, override

from publisher.log_publisher import ConsolePublisher

if TYPE_CHECKING:
    from configuration import Configuration
    from publisher.core import WirePayload

LOG = logging.getLogger(__name__)


class MessageCapturingConsolePublisher(ConsolePublisher):
    def __init__(self, configuration: Configuration) -> None:
        super().__init__(configuration)
        # Test inspection map; consumers narrow per-key (e.g. json.loads on
        # serialized dict topics), so keep the value type permissive here.
        self.map: dict[str, Any] = {}
        self.publish_count: dict[str, int] = {}

    @override
    def internal_publish(
        self, key: str, value: WirePayload | None, *, retain: bool = True
    ) -> None:
        self.map[key] = value
        self.publish_count[key] = self.publish_count.get(key, 0) + 1
        LOG.debug(f"{key}: {value} (retain={retain})")
