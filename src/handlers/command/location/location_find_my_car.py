from __future__ import annotations

import logging
from typing import TYPE_CHECKING, override

from handlers.command.base import MultiValuedCommandHandler
import mqtt_topics

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

LOG = logging.getLogger(__name__)


class LocationFindMyCarCommand(MultiValuedCommandHandler[None]):
    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.LOCATION_FIND_MY_CAR_SET

    @override
    def options(self) -> dict[str, Callable[[], Awaitable[None]]]:
        return {
            "activate": self.__handle_activate,
            "lights_only": self.__handle_lights_only,
            "horn_only": self.__handle_horn_only,
            "stop": self.__handle_stop,
        }

    async def __handle_activate(self) -> None:
        LOG.info(
            f"Activating 'find my car' with horn and lights for vehicle {self.vin}"
        )
        await self.saic_api.control_find_my_car(self.vin)

    async def __handle_lights_only(self) -> None:
        LOG.info(f"Activating 'find my car' with lights only for vehicle {self.vin}")
        await self.saic_api.control_find_my_car(
            self.vin, with_horn=False, with_lights=True
        )

    async def __handle_horn_only(self) -> None:
        LOG.info(f"Activating 'find my car' with horn only for vehicle {self.vin}")
        await self.saic_api.control_find_my_car(
            self.vin, with_horn=True, with_lights=False
        )

    async def __handle_stop(self) -> None:
        LOG.info(f"Stopping 'find my car' for vehicle {self.vin}")
        await self.saic_api.control_find_my_car(self.vin, should_stop=True)
