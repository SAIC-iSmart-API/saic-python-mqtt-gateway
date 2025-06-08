from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

from saic_ismart_client_ng.exceptions import SaicApiException, SaicLogoutException

from exceptions import MqttGatewayException
from handlers.command import ALL_COMMAND_HANDLERS, CommandHandlerBase
import mqtt_topics
from vehicle import RefreshMode

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from saic_ismart_client_ng import SaicApi

    from handlers.relogin import ReloginHandler
    from publisher.core import Publisher
    from vehicle import VehicleState

    CommandHandler = Callable[[str], Awaitable[bool]]

LOG = logging.getLogger(__name__)


class VehicleCommandHandler:
    def __init__(
        self,
        *,
        vehicle_state: VehicleState,
        saic_api: SaicApi,
        relogin_handler: ReloginHandler,
        mqtt_topic: str,
        vehicle_prefix: str,
    ) -> None:
        self.vehicle_state: Final[VehicleState] = vehicle_state
        self.saic_api: Final[SaicApi] = saic_api
        self.relogin_handler: Final[ReloginHandler] = relogin_handler
        self.global_mqtt_topic: Final[str] = mqtt_topic
        self.vehicle_prefix: Final[str] = vehicle_prefix
        self.__command_handlers = {
            handler.topic(): handler(self.saic_api, self.vehicle_state)
            for handler in ALL_COMMAND_HANDLERS
        }

    @property
    def publisher(self) -> Publisher:
        return self.vehicle_state.publisher

    async def handle_mqtt_command(self, *, topic: str, payload: str) -> None:
        topic, result_topic = self.__get_command_topics(topic)
        handler = self.__command_handlers.get(topic)
        if not handler:
            msg = f"No handler found for command topic {topic}"
            self.publisher.publish_str(result_topic, msg)
            LOG.error(msg)
        else:
            await self.__execute_mqtt_command_handler(
                handler=handler, payload=payload, topic=topic, result_topic=result_topic
            )

    async def __execute_mqtt_command_handler(
        self,
        *,
        handler: CommandHandlerBase,
        payload: str,
        topic: str,
        result_topic: str,
    ) -> None:
        try:
            should_force_refresh = await handler.handle(payload)
            self.publisher.publish_str(result_topic, "Success")
            if should_force_refresh:
                self.vehicle_state.set_refresh_mode(
                    RefreshMode.FORCE, f"after command execution on topic {topic}"
                )
        except MqttGatewayException as e:
            self.publisher.publish_str(result_topic, f"Failed: {e.message}")
            LOG.exception(e.message, exc_info=e)
        except SaicLogoutException as se:
            self.publisher.publish_str(result_topic, f"Failed: {se.message}")
            LOG.error("API Client was logged out, waiting for a new login", exc_info=se)
            self.relogin_handler.relogin()
        except SaicApiException as se:
            self.publisher.publish_str(result_topic, f"Failed: {se.message}")
            LOG.exception(se.message, exc_info=se)
        except Exception as se:
            self.publisher.publish_str(result_topic, "Failed unexpectedly")
            LOG.exception(
                "handle_mqtt_command failed with an unexpected exception", exc_info=se
            )

    def __get_command_topics(self, topic: str) -> tuple[str, str]:
        global_topic_removed = topic.removeprefix(self.global_mqtt_topic).removeprefix(
            "/"
        )
        set_topic = global_topic_removed.removeprefix(self.vehicle_prefix).removeprefix(
            "/"
        )
        result_topic = (
            global_topic_removed.removesuffix(mqtt_topics.SET_SUFFIX).removesuffix("/")
            + "/"
            + mqtt_topics.RESULT_SUFFIX
        )
        return set_topic, result_topic
