from __future__ import annotations

import logging
from typing import override

from handlers.command.base import BooleanCommandHandler
import mqtt_topics

LOG = logging.getLogger(__name__)


class DoorsLockedCommand(BooleanCommandHandler[None]):
    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.DOORS_LOCKED_SET

    @override
    async def handle_true(self) -> None:
        LOG.info(f"Vehicle {self.vin} will be locked")
        await self.saic_api.lock_vehicle(self.vin)

    @override
    async def handle_false(self) -> None:
        LOG.info(f"Vehicle {self.vin} will be unlocked")
        await self.saic_api.unlock_vehicle(self.vin)
