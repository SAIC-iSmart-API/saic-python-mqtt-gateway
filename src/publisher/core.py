from __future__ import annotations

from abc import ABC, abstractmethod
import json
import re
from typing import TYPE_CHECKING, Any, TypeVar

import mqtt_topics

if TYPE_CHECKING:
    from configuration import Configuration

T = TypeVar("T")


class MqttCommandListener(ABC):
    @abstractmethod
    async def on_mqtt_command_received(
        self, *, vin: str, topic: str, payload: str
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
    def is_connected(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def publish_json(
        self, key: str, data: dict[str, Any], no_prefix: bool = False
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def publish_str(self, key: str, value: str, no_prefix: bool = False) -> None:
        raise NotImplementedError

    @abstractmethod
    def publish_int(self, key: str, value: int, no_prefix: bool = False) -> None:
        raise NotImplementedError

    @abstractmethod
    def publish_bool(self, key: str, value: bool, no_prefix: bool = False) -> None:
        raise NotImplementedError

    @abstractmethod
    def publish_float(self, key: str, value: float, no_prefix: bool = False) -> None:
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
                            | "event_id"
                            | "eventID"
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
        elements = device_id.split("###")
        return f"{self.anonymize_str(elements[0])}###{self.anonymize_str(elements[1])}"

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
