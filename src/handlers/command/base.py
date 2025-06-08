from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Final, override

from exceptions import MqttGatewayException

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from saic_ismart_client_ng import SaicApi

    from publisher.core import Publisher
    from vehicle import VehicleState


class CommandHandlerBase(metaclass=ABCMeta):
    def __init__(self, saic_api: SaicApi, vehicle_state: VehicleState) -> None:
        self.__saic_api: Final[SaicApi] = saic_api
        self.__vehicle_state: Final[VehicleState] = vehicle_state

    @classmethod
    def name(cls) -> str:
        return cls.__name__

    @classmethod
    @abstractmethod
    def topic(cls) -> str:
        raise NotImplementedError

    @abstractmethod
    async def handle(self, payload: str) -> bool:
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
    async def should_refresh(self, _action_result: T) -> bool:
        return True

    @abstractmethod
    def options(self) -> dict[str, Callable[[], Awaitable[T]]]:
        raise NotImplementedError

    @override
    async def handle(self, payload: str) -> bool:
        normalized_payload = payload.strip().lower()
        options = self.options()
        option_handler = options.get(normalized_payload)
        if option_handler is None:
            msg = f"Unsupported payload {payload} for command {self.name()}"
            raise MqttGatewayException(msg)
        response = await option_handler()
        return await self.should_refresh(response)


class BooleanCommandHandler[T](CommandHandlerBase, metaclass=ABCMeta):
    @abstractmethod
    async def handle_true(self) -> T:
        raise NotImplementedError

    @abstractmethod
    async def handle_false(self) -> T:
        raise NotImplementedError

    async def should_refresh(self, _action_result: T) -> bool:
        return True

    @override
    async def handle(self, payload: str) -> bool:
        match payload.strip().lower():
            case "true" | "1" | "on":
                response = await self.handle_true()
            case "false" | "0" | "off":
                response = await self.handle_false()
            case _:
                msg = f"Unsupported payload {payload} for command {self.name()}"
                raise MqttGatewayException(msg)
        return await self.should_refresh(response)


class PayloadConvertingCommandHandler[T](CommandHandlerBase, metaclass=ABCMeta):
    @staticmethod
    @abstractmethod
    def convert_payload(payload: str) -> T:
        raise NotImplementedError

    @abstractmethod
    async def handle_typed_payload(self, payload: T) -> bool:
        raise NotImplementedError

    @override
    async def handle(self, payload: str) -> bool:
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
