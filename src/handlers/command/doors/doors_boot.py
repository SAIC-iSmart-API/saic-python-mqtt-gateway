from __future__ import annotations

import logging
from typing import override

from handlers.command.base import BooleanCommandHandler
import mqtt_topics

LOG = logging.getLogger(__name__)


class DoorsBootCommand(BooleanCommandHandler[None]):
    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.DOORS_BOOT_SET

    @override
    async def handle_true(self) -> None:
        LOG.info(f"We cannot lock vehicle {self.vin} boot remotely")

    @override
    async def handle_false(self) -> None:
        LOG.info(f"Vehicle {self.vin} boot will be unlocked")
        await self.saic_api.open_tailgate(self.vin)
