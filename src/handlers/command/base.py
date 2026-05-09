from __future__ import annotations

from abc import ABCMeta, abstractmethod
import dataclasses
from typing import TYPE_CHECKING, Final, override

from exceptions import MqttGatewayException

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from saic_ismart_client_ng import SaicApi

    from publisher.core import Publisher
    from vehicle import VehicleState


@dataclasses.dataclass(kw_only=True, frozen=True)
class CommandProcessingResult:
    force_refresh: bool
    clear_command: bool


RESULT_DO_NOTHING: Final[CommandProcessingResult] = CommandProcessingResult(
    force_refresh=False, clear_command=False
)
RESULT_REFRESH_AND_CLEAR: Final[CommandProcessingResult] = CommandProcessingResult(
    force_refresh=True, clear_command=True
)
RESULT_CLEAR_ONLY: Final[CommandProcessingResult] = CommandProcessingResult(
    force_refresh=False, clear_command=True
)
RESULT_REFRESH_ONLY: Final[CommandProcessingResult] = CommandProcessingResult(
    force_refresh=True, clear_command=False
)


class CommandHandlerBase(metaclass=ABCMeta):
    def __init__(self, saic_api: SaicApi, vehicle_state: VehicleState) -> None:
        self.__saic_api: Final[SaicApi] = saic_api
        self.__vehicle_state: Final[VehicleState] = vehicle_state

    @classmethod
    def name(cls) -> str:
        return cls.__name__

    @classmethod
    def is_replayable_when_retained(cls) -> bool:
        """Whether the dispatcher may invoke this handler with retained=True.

        Default False: action-bearing commands (charging start/stop, locks,
        climate, FORCE refresh, etc.) would re-fire on every gateway restart
        if their `/set` topic was retained on the broker, so the dispatcher
        drops the replay before the handler runs. Override to True only on
        idempotent value-bearing handlers whose HA discovery payload also
        declares `retain: true`.
        """
        return False

    @classmethod
    @abstractmethod
    def topic(cls) -> str:
        raise NotImplementedError

    @abstractmethod
    async def handle(
        self, payload: str, *, retained: bool = False
    ) -> CommandProcessingResult:
        raise NotImplementedError

    @property
    def saic_api(self) -> SaicApi:
        return self.__saic_api

    @property
    def vehicle_state(self) -> VehicleState:
        return self.__vehicle_state

    @property
    def vin(self) -> str:
        return self.__vehicle_state.vin

    @property
    def publisher(self) -> Publisher:
        return self.__vehicle_state.publisher


class MultiValuedCommandHandler[T](CommandHandlerBase, metaclass=ABCMeta):
    @abstractmethod
    async def _get_action_result(self, _action_result: T) -> CommandProcessingResult:
        pass

    @abstractmethod
    def options(self) -> dict[str, Callable[[], Awaitable[T]]]:
        raise NotImplementedError

    @property
    def supports_empty_payload(self) -> bool:
        return False

    @override
    async def handle(
        self,
        payload: str,
        *,
        retained: bool = False,
    ) -> CommandProcessingResult:
        normalized_payload = payload.strip().lower()

        if len(normalized_payload) == 0 and not self.supports_empty_payload:
            return RESULT_DO_NOTHING

        options = self.options()
        option_handler = options.get(normalized_payload)
        if option_handler is None:
            msg = f"Unsupported payload {payload} for command {self.name()}"
            raise MqttGatewayException(msg)
        response = await option_handler()
        return await self._get_action_result(response)


class BooleanCommandHandler[T](CommandHandlerBase, metaclass=ABCMeta):
    @abstractmethod
    async def handle_true(self) -> T:
        raise NotImplementedError

    @abstractmethod
    async def handle_false(self) -> T:
        raise NotImplementedError

    @abstractmethod
    async def _get_action_result(self, _action_result: T) -> CommandProcessingResult:
        pass

    @override
    async def handle(
        self,
        payload: str,
        *,
        retained: bool = False,
    ) -> CommandProcessingResult:
        normalized_payload = payload.strip().lower()

        if len(normalized_payload) == 0:
            return RESULT_DO_NOTHING

        match normalized_payload:
            case "true" | "1" | "on":
                response = await self.handle_true()
            case "false" | "0" | "off":
                response = await self.handle_false()
            case _:
                msg = f"Unsupported payload {payload} for command {self.name()}"
                raise MqttGatewayException(msg)
        return await self._get_action_result(response)


class PayloadConvertingCommandHandler[T](CommandHandlerBase, metaclass=ABCMeta):
    @staticmethod
    @abstractmethod
    def convert_payload(payload: str) -> T:
        raise NotImplementedError

    @abstractmethod
    async def handle_typed_payload(self, payload: T) -> CommandProcessingResult:
        raise NotImplementedError

    @property
    def supports_empty_payload(self) -> bool:
        return False

    @override
    async def handle(
        self,
        payload: str,
        *,
        retained: bool = False,
    ) -> CommandProcessingResult:
        if len(payload.strip()) == 0 and not self.supports_empty_payload:
            return RESULT_DO_NOTHING

        try:
            converted_payload = self.convert_payload(payload)
        except Exception as e:
            msg = f"Error converting payload {payload} for command {self.name()}"
            raise MqttGatewayException(msg) from e

        return await self.handle_typed_payload(converted_payload)


class IntCommandHandler(PayloadConvertingCommandHandler[int], metaclass=ABCMeta):
    @staticmethod
    def convert_payload(payload: str) -> int:
        return int(payload.strip().lower())


class FloatCommandHandler(PayloadConvertingCommandHandler[float], metaclass=ABCMeta):
    @staticmethod
    def convert_payload(payload: str) -> float:
        return float(payload.strip().lower())
