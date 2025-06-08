from __future__ import annotations

import logging
from typing import override

from handlers.command.base import BooleanCommandHandler
import mqtt_topics

LOG = logging.getLogger(__name__)


class ClimateBackWindowHeatCommand(BooleanCommandHandler[None]):
    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.CLIMATE_BACK_WINDOW_HEAT_SET

    @override
    async def handle_true(self) -> None:
        LOG.info("Rear window heating will be switched on")
        await self.saic_api.control_rear_window_heat(self.vin, enable=True)

    @override
    async def handle_false(self) -> None:
        LOG.info("Rear window heating will be switched off")
        await self.saic_api.control_rear_window_heat(self.vin, enable=False)
