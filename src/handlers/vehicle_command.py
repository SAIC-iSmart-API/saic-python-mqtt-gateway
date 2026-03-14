from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Any, Final

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


@dataclass(frozen=True, kw_only=True)
class _MqttCommandTopic:
    command: str
    command_no_global: str
    command_no_vin: str
    response_no_global: str


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

    def __report_command_failure(
        self,
        *,
        command: str,
        result_topic: str,
        detail: str,
        exc: Exception | None = None,
    ) -> None:
        if exc is not None:
            LOG.exception("Command %s failed: %s", command, detail, exc_info=exc)
        else:
            LOG.error("Command %s failed: %s", command, detail)
        try:
            self.publisher.publish_str(result_topic, f"Failed: {detail}")
        except Exception:
            LOG.warning(
                "Failed to publish failure result for command %s",
                command,
                exc_info=True,
            )
        try:
            error_topic = self.vehicle_state.get_topic(mqtt_topics.COMMAND_ERROR)
            event_payload: dict[str, Any] = {
                "event_type": "command_error",
                "command": command,
                "detail": detail,
            }
            self.publisher.publish_json(error_topic, event_payload)
        except Exception:
            LOG.warning(
                "Failed to publish command error event for command %s",
                command,
                exc_info=True,
            )

    async def handle_mqtt_command(self, *, topic: str, payload: str) -> None:
        analyzed_topic = self.__get_command_topics(topic)
        handler = self.__command_handlers.get(analyzed_topic.command_no_vin)
        if not handler:
            msg = f"No handler found for command topic {analyzed_topic.command_no_vin}"
            self.__report_command_failure(
                command=analyzed_topic.command_no_vin,
                result_topic=analyzed_topic.response_no_global,
                detail=msg,
            )
        else:
            await self.__execute_mqtt_command_handler(
                handler=handler, payload=payload, analyzed_topic=analyzed_topic
            )

    async def __execute_mqtt_command_handler(
        self,
        *,
        handler: CommandHandlerBase,
        payload: str,
        analyzed_topic: _MqttCommandTopic,
    ) -> None:
        topic = analyzed_topic.command_no_vin
        topic_no_global = analyzed_topic.command_no_global
        result_topic = analyzed_topic.response_no_global

        try:
            execution_result = await handler.handle(payload)
            self.publisher.publish_str(result_topic, "Success")
            if execution_result.force_refresh:
                self.vehicle_state.set_refresh_mode(
                    RefreshMode.FORCE, f"after command execution on topic {topic}"
                )
            if execution_result.clear_command:
                self.publisher.clear_topic(topic_no_global)
        except MqttGatewayException as e:
            self.__report_command_failure(
                command=topic, result_topic=result_topic, detail=e.message, exc=e
            )
        except SaicLogoutException:
            LOG.warning(
                "API Client was logged out, attempting immediate relogin and retry"
            )
            try:
                await self.relogin_handler.force_login()
            except Exception as login_err:
                self.__report_command_failure(
                    command=topic,
                    result_topic=result_topic,
                    detail=f"relogin failed ({login_err})",
                    exc=login_err,
                )
                return
            try:
                execution_result = await handler.handle(payload)
                self.publisher.publish_str(result_topic, "Success")
                if execution_result.force_refresh:
                    self.vehicle_state.set_refresh_mode(
                        RefreshMode.FORCE,
                        f"after command execution on topic {topic}",
                    )
                if execution_result.clear_command:
                    self.publisher.clear_topic(topic_no_global)
            except Exception as retry_err:
                self.__report_command_failure(
                    command=topic,
                    result_topic=result_topic,
                    detail=str(retry_err),
                    exc=retry_err,
                )
        except SaicApiException as se:
            self.__report_command_failure(
                command=topic, result_topic=result_topic, detail=se.message, exc=se
            )
        except Exception as e:
            self.__report_command_failure(
                command=topic,
                result_topic=result_topic,
                detail="unexpected error",
                exc=e,
            )

    def __get_command_topics(self, topic: str) -> _MqttCommandTopic:
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
        return _MqttCommandTopic(
            command=topic,
            command_no_global=global_topic_removed,
            command_no_vin=set_topic,
            response_no_global=result_topic,
        )
