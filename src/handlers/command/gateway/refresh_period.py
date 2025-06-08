from __future__ import annotations

from typing import override

from handlers.command.base import IntCommandHandler
import mqtt_topics


class RefreshPeriodActiveCommand(IntCommandHandler):
    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.REFRESH_PERIOD_ACTIVE_SET

    @override
    async def handle_typed_payload(self, payload: int) -> bool:
        self.vehicle_state.set_refresh_period_active(payload)
        return False


class RefreshPeriodInactiveCommand(IntCommandHandler):
    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.REFRESH_PERIOD_INACTIVE_SET

    @override
    async def handle_typed_payload(self, payload: int) -> bool:
        self.vehicle_state.set_refresh_period_inactive(payload)
        return False


class RefreshPeriodInactiveGraceCommand(IntCommandHandler):
    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.REFRESH_PERIOD_INACTIVE_GRACE_SET

    @override
    async def handle_typed_payload(self, payload: int) -> bool:
        self.vehicle_state.set_refresh_period_inactive_grace(payload)
        return False


class RefreshPeriodAfterShutdownCommand(IntCommandHandler):
    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.REFRESH_PERIOD_AFTER_SHUTDOWN_SET

    @override
    async def handle_typed_payload(self, payload: int) -> bool:
        self.vehicle_state.set_refresh_period_after_shutdown(payload)
        return False
