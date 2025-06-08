from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Collection


class HaCustomAvailabilityConfig:
    def __init__(
        self,
        *,
        rules: list[HaCustomAvailabilityEntry],
        mode: str = "all",
    ) -> None:
        self.__rules = rules
        self.__mode = mode

    def to_dict(self) -> dict[str, Any]:
        return {
            "availability": [r.to_dict() for r in set(self.__rules)],
            "availability_mode": self.__mode,
        }


class HaCustomAvailabilityEntry:
    def __init__(
        self,
        *,
        topic: str,
        template: str | None = None,
        payload_available: str = "online",
        payload_not_available: str = "offline",
    ) -> None:
        self.__topic = topic
        self.__template = template
        self.__payload_available = payload_available
        self.__payload_not_available = payload_not_available

    def to_dict(self) -> dict[str, Any]:
        result = {
            "topic": self.__topic,
            "payload_available": self.__payload_available,
            "payload_not_available": self.__payload_not_available,
        }
        if self.__template:
            result.update({"value_template": self.__template})
        return result

    def __key(self) -> Collection[str | None]:
        return (
            self.__topic,
            self.__template,
            self.__payload_available,
            self.__payload_not_available,
        )

    def __hash__(self) -> int:
        return hash(self.__key())

    def __eq__(self, other: object) -> bool:
        if isinstance(other, HaCustomAvailabilityEntry):
            return self.__key() == other.__key()
        return NotImplemented
