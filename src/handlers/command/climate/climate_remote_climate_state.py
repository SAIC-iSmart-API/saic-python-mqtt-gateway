from __future__ import annotations

import logging
from typing import TYPE_CHECKING, override

from handlers.command.base import MultiValuedCommandHandler
import mqtt_topics

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

LOG = logging.getLogger(__name__)


class ClimateRemoteClimateStateCommand(MultiValuedCommandHandler[None]):
    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE_SET

    @override
    def options(self) -> dict[str, Callable[[], Awaitable[None]]]:
        return {
            "off": self.__stop_ac,
            "blowingonly": self.__start_ac_blowing,
            "on": self.__start_ac,
            "front": self.__start_front_defrost,
        }

    async def __start_front_defrost(self) -> None:
        LOG.info("A/C will be set to front seats only")
        await self.saic_api.start_front_defrost(self.vin)

    async def __start_ac(self) -> None:
        LOG.info("A/C will be switched on")
        await self.saic_api.start_ac(
            self.vin,
            temperature_idx=self.vehicle_state.get_ac_temperature_idx(),
        )

    async def __start_ac_blowing(self) -> None:
        LOG.info("A/C will be set to blowing only")
        await self.saic_api.start_ac_blowing(self.vin)

    async def __stop_ac(self) -> None:
        LOG.info("A/C will be switched off")
        await self.saic_api.stop_ac(self.vin)
