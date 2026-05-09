from __future__ import annotations

import logging
from typing import override

from exceptions import MqttGatewayException
from handlers.command.base import (
    RESULT_DO_NOTHING,
    CommandProcessingResult,
    PayloadConvertingCommandHandler,
)
import mqtt_topics
from vehicle import ONE_SHOT_REFRESH_MODES, RefreshMode

LOG = logging.getLogger(__name__)


class RefreshModeCommand(PayloadConvertingCommandHandler[RefreshMode]):
    @classmethod
    @override
    def is_replayable_when_retained(cls) -> bool:
        # OFF / PERIODIC are persistent user choices; one-shots dropped in handle().
        return True

    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.REFRESH_MODE_SET

    @staticmethod
    @override
    def convert_payload(payload: str) -> RefreshMode:
        normalized_payload = payload.strip().lower()
        return RefreshMode.get(normalized_payload)

    @override
    async def handle(
        self, payload: str, *, retained: bool = False
    ) -> CommandProcessingResult:
        if len(payload.strip()) == 0 and not self.supports_empty_payload:
            return RESULT_DO_NOTHING
        try:
            refresh_mode = self.convert_payload(payload)
        except Exception as e:
            msg = f"Error converting payload {payload} for command {self.name()}"
            raise MqttGatewayException(msg) from e
        if retained and refresh_mode in ONE_SHOT_REFRESH_MODES:
            # Retained one-shot modes would re-fire on every gateway restart.
            LOG.info(
                "Dropping retained one-shot refresh mode %s for VIN %s",
                refresh_mode.value,
                self.vin,
            )
            return RESULT_DO_NOTHING
        return await self.handle_typed_payload(refresh_mode)

    @override
    async def handle_typed_payload(
        self, refresh_mode: RefreshMode
    ) -> CommandProcessingResult:
        self.vehicle_state.set_refresh_mode(
            refresh_mode, "MQTT direct set refresh mode command execution"
        )
        return RESULT_DO_NOTHING
