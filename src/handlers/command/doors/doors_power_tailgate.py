from __future__ import annotations

import logging
from typing import TYPE_CHECKING, override

from saic_ismart_client_ng.api.vehicle.locks import TailgateAction

from handlers.command.base import (
    RESULT_REFRESH_AND_CLEAR,
    CommandProcessingResult,
    MultiValuedCommandHandler,
)
import mqtt_topics

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

LOG = logging.getLogger(__name__)


class DoorsPowerTailgateCommand(MultiValuedCommandHandler[None]):
    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.DOORS_BOOT_POWER_TAILGATE_SET

    @override
    def options(self) -> dict[str, Callable[[], Awaitable[None]]]:
        return {
            "open": lambda: self.__control_tailgate(TailgateAction.OPEN),
            "close": lambda: self.__control_tailgate(TailgateAction.CLOSE),
        }

    async def __control_tailgate(self, action: TailgateAction) -> None:
        # Sent to every car: nothing in the vehicle data tells which cars have
        # a power tailgate. Cars without one are expected to refuse it.
        LOG.info(f"Vehicle {self.vin} power tailgate will {action.name.lower()}")
        await self.saic_api.control_tailgate(self.vin, action=action)

    @override
    async def _get_action_result(self, _action_result: None) -> CommandProcessingResult:
        return RESULT_REFRESH_AND_CLEAR
