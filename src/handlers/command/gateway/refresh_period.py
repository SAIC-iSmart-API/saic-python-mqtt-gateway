from __future__ import annotations

from typing import override

from handlers.command.base import (
    RESULT_DO_NOTHING,
    CommandProcessingResult,
    IntCommandHandler,
)
import mqtt_topics


class RefreshPeriodActiveCommand(IntCommandHandler):
    @classmethod
    @override
    def is_replayable_when_retained(cls) -> bool:
        return True

    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.REFRESH_PERIOD_ACTIVE_SET

    @override
    async def handle_typed_payload(self, payload: int) -> CommandProcessingResult:
        self.vehicle_state.set_refresh_period_active(payload)
        return RESULT_DO_NOTHING


class RefreshPeriodInactiveCommand(IntCommandHandler):
    @classmethod
    @override
    def is_replayable_when_retained(cls) -> bool:
        return True

    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.REFRESH_PERIOD_INACTIVE_SET

    @override
    async def handle_typed_payload(self, payload: int) -> CommandProcessingResult:
        self.vehicle_state.set_refresh_period_inactive(payload)
        return RESULT_DO_NOTHING


class RefreshPeriodInactiveGraceCommand(IntCommandHandler):
    @classmethod
    @override
    def is_replayable_when_retained(cls) -> bool:
        return True

    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.REFRESH_PERIOD_INACTIVE_GRACE_SET

    @override
    async def handle_typed_payload(self, payload: int) -> CommandProcessingResult:
        self.vehicle_state.set_refresh_period_inactive_grace(payload)
        return RESULT_DO_NOTHING


class RefreshPeriodAfterShutdownCommand(IntCommandHandler):
    @classmethod
    @override
    def is_replayable_when_retained(cls) -> bool:
        return True

    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.REFRESH_PERIOD_AFTER_SHUTDOWN_SET

    @override
    async def handle_typed_payload(self, payload: int) -> CommandProcessingResult:
        self.vehicle_state.set_refresh_period_after_shutdown(payload)
        return RESULT_DO_NOTHING
