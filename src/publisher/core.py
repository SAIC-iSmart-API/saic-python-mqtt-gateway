from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
import json
import re
from typing import TYPE_CHECKING, Any, TypeVar

import mqtt_topics
from utils import datetime_to_str

if TYPE_CHECKING:
    from configuration import Configuration

T = TypeVar("T")

type Publishable = bool | int | float | str | dict[str, Any] | datetime
"""Closed union of value types this gateway knows how to publish to MQTT.

Mirrors the typed `publish_*` methods on :class:`Publisher` plus the `dict`
shape handled by `publish_json`, and `datetime`, which is stringified via
:func:`utils.datetime_to_str`. Use it at signature boundaries when a caller
holds "something publishable" without statically knowing which arm.
"""

type WirePayload = bool | int | float | str
"""Primitive subset of :data:`Publishable` that reaches the transport layer.

After the typed `publish_*` methods do their work (`publish_json` serializes
dicts to JSON strings, `publish_datetime` stringifies via
:func:`utils.datetime_to_str`), only these scalar arms cross the
publisher/transport boundary. Use `WirePayload | None` for wire-level helpers
where `None` means "clear the retained message."
"""


class MqttCommandListener(ABC):
    @abstractmethod
    async def on_mqtt_command_received(
        self, *, vin: str, topic: str, payload: str, retained: bool = False
    ) -> None:
        raise NotImplementedError("Should have implemented this")

    @abstractmethod
    async def on_charging_detected(self, vin: str) -> None:
        raise NotImplementedError("Should have implemented this")

    @abstractmethod
    async def on_mqtt_global_command_received(
        self, *, topic: str, payload: str
    ) -> None:
        raise NotImplementedError("Should have implemented this")

    @abstractmethod
    async def on_charging_station_energy_imported(
        self, vin: str, imported_energy_wh: float
    ) -> None:
        raise NotImplementedError("Should have implemented this")

    @abstractmethod
    async def on_charger_connection_state_changed(
        self, vin: str, connected: bool
    ) -> None:
        raise NotImplementedError("Should have implemented this")

    def on_mqtt_reconnected(self) -> None:  # noqa: B027
        """Reset state when the MQTT client reconnects after a connection loss.

        This is intentionally synchronous because it is called from gmqtt's
        synchronous on_connect callback. It is also intentionally not abstract
        so that implementations can opt in without being forced to override.
        """


class Publisher(ABC):
    def __init__(self, config: Configuration) -> None:
        self.__configuration = config
        self.__command_listener: MqttCommandListener | None = None
        if config.mqtt_allow_dots_in_topic:
            self.__invalid_mqtt_chars = re.compile(r"[+#*$>]")
        else:
            self.__invalid_mqtt_chars = re.compile(r"[+#*$>.]")
        self.__topic_root = self.__remove_special_mqtt_characters(config.mqtt_topic)

    @abstractmethod
    async def connect(self) -> None:
        pass

    @abstractmethod
    def enable_commands(self) -> None:
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def publish_json(
        self,
        key: str,
        data: dict[str, Any],
        no_prefix: bool = False,
        *,
        retain: bool = True,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def publish_str(
        self, key: str, value: str, no_prefix: bool = False, *, retain: bool = True
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def publish_int(
        self, key: str, value: int, no_prefix: bool = False, *, retain: bool = True
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def publish_bool(
        self, key: str, value: bool, no_prefix: bool = False, *, retain: bool = True
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def publish_float(
        self, key: str, value: float, no_prefix: bool = False, *, retain: bool = True
    ) -> None:
        raise NotImplementedError

    def publish_datetime(
        self,
        key: str,
        value: datetime,
        no_prefix: bool = False,
        *,
        retain: bool = True,
    ) -> None:
        """Stringify a datetime via :func:`utils.datetime_to_str` and publish."""
        self.publish_str(key, datetime_to_str(value), no_prefix, retain=retain)

    def publish(
        self,
        key: str,
        value: Publishable,
        no_prefix: bool = False,
        *,
        retain: bool = True,
    ) -> None:
        """Dispatch to the appropriate typed publish_* based on value type.

        For callers that hold a `Publishable` without statically knowing
        which arm of the union it is. `retain` is forwarded to every arm.
        """
        # bool must precede int: isinstance(True, int) is True in Python.
        if isinstance(value, bool):
            self.publish_bool(key, value, no_prefix, retain=retain)
        elif isinstance(value, int):
            self.publish_int(key, value, no_prefix, retain=retain)
        elif isinstance(value, float):
            self.publish_float(key, value, no_prefix, retain=retain)
        elif isinstance(value, str):
            self.publish_str(key, value, no_prefix, retain=retain)
        elif isinstance(value, dict):
            self.publish_json(key, value, no_prefix, retain=retain)
        elif isinstance(value, datetime):
            self.publish_datetime(key, value, no_prefix, retain=retain)
        else:
            # Defensive: type system rules this out, but `Any` callers can sneak
            # an unsupported runtime type through; raise rather than silently no-op.
            msg = f"Unsupported value type: {type(value).__name__}"  # type: ignore[unreachable]
            raise TypeError(msg)

    @abstractmethod
    def clear_topic(self, key: str, no_prefix: bool = False) -> None:
        raise NotImplementedError

    def get_mqtt_account_prefix(self) -> str:
        return self.__remove_special_mqtt_characters(
            f"{self.__topic_root}/{self.configuration.saic_user}"
        )

    def get_topic(self, key: str, no_prefix: bool) -> str:
        topic = key if no_prefix else f"{self.__topic_root}/{key}"
        return self.__remove_special_mqtt_characters(topic)

    def __remove_special_mqtt_characters(self, input_str: str) -> str:
        return self.__invalid_mqtt_chars.sub("_", input_str)

    def __remove_byte_strings(self, data: dict[str, Any]) -> dict[str, Any]:
        for key in data:  # noqa: PLC0206
            if isinstance(data[key], bytes):
                data[key] = str(data[key])
            elif isinstance(data[key], dict):
                data[key] = self.__remove_byte_strings(data[key])
            elif isinstance(data[key], list):
                for item in data[key]:
                    if isinstance(item, dict):
                        self.__remove_byte_strings(item)
        return data

    def __anonymize(self, data: T) -> T:
        if isinstance(data, dict):
            for key in data:
                if isinstance(data[key], str):
                    match key:
                        case "password":
                            data[key] = "******"
                        case (
                            "uid"
                            | "email"
                            | "user_name"
                            | "account"
                            | "ping"
                            | "token"
                            | "access_token"
                            | "refreshToken"
                            | "refresh_token"
                            | "vin"
                        ):
                            data[key] = Publisher.anonymize_str(data[key])
                        case "deviceId":
                            data[key] = self.anonymize_device_id(data[key])
                        case (
                            "seconds"
                            | "bindTime"
                            | "eventCreationTime"
                            | "latitude"
                            | "longitude"
                        ):
                            data[key] = Publisher.anonymize_int(data[key])
                        case (
                            "eventID"
                            | "event-id"
                            | "event_id"
                            | "eventId"
                            | "lastKeySeen"
                        ):
                            data[key] = 9999
                        case "content":
                            data[key] = re.sub(
                                "\\(\\*\\*\\*...\\)", "(***XXX)", data[key]
                            )
                elif isinstance(data[key], dict):
                    data[key] = self.__anonymize(data[key])
                elif isinstance(data[key], list | set | tuple):
                    data[key] = [self.__anonymize(item) for item in data[key]]
        return data

    def keepalive(self) -> None:
        self.publish_str(mqtt_topics.INTERNAL_LWT, "online", False)

    @staticmethod
    def anonymize_str(value: str) -> str:
        r = re.sub("[a-zA-Z]", "X", value)
        return re.sub("[1-9]", "9", r)

    def anonymize_device_id(self, device_id: str) -> str:
        elements = device_id.split("###", maxsplit=1)
        if len(elements) == 2:
            return (
                f"{self.anonymize_str(elements[0])}###{self.anonymize_str(elements[1])}"
            )
        return self.anonymize_str(device_id)

    @staticmethod
    def anonymize_int(value: int) -> int:
        return int(value / 100000 * 100000)

    def dict_to_anonymized_json(self, data: dict[str, Any]) -> str:
        no_binary_strings = self.__remove_byte_strings(data)
        if self.configuration.anonymized_publishing:
            result = self.__anonymize(no_binary_strings)
        else:
            result = no_binary_strings
        return json.dumps(result, indent=2)

    @property
    def configuration(self) -> Configuration:
        return self.__configuration

    @property
    def command_listener(self) -> MqttCommandListener | None:
        return self.__command_listener

    @command_listener.setter
    def command_listener(self, listener: MqttCommandListener) -> None:
        self.__command_listener = listener
