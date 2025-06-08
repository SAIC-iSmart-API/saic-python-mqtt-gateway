from __future__ import annotations

import logging
from typing import override

from handlers.command.base import BooleanCommandHandler
import mqtt_topics

LOG = logging.getLogger(__name__)


class ClimateFrontWindowHeatCommand(BooleanCommandHandler[None]):
    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.CLIMATE_FRONT_WINDOW_HEAT_SET

    @override
    async def handle_true(self) -> None:
        LOG.info("Front window heating will be switched on")
        await self.saic_api.start_front_defrost(self.vin)

    @override
    async def handle_false(self) -> None:
        LOG.info("Front window heating will be switched off")
        await self.saic_api.stop_ac(self.vin)
