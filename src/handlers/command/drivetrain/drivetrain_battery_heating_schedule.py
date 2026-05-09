from __future__ import annotations

from dataclasses import dataclass
from datetime import time
import json
import logging
from typing import TYPE_CHECKING, Any, override

from handlers.command.base import (
    RESULT_REFRESH_ONLY,
    CommandProcessingResult,
    PayloadConvertingCommandHandler,
)
import mqtt_topics

if TYPE_CHECKING:
    from collections.abc import Mapping

LOG = logging.getLogger(__name__)


@dataclass
class BatteryHeatingScheduleCommandPayload:
    start_time: time
    enable: bool

    @staticmethod
    def from_json(
        payload_json: Mapping[str, Any],
    ) -> BatteryHeatingScheduleCommandPayload:
        return BatteryHeatingScheduleCommandPayload(
            time.fromisoformat(payload_json["startTime"]),
            payload_json["mode"].upper() == "ON",
        )


class DrivetrainBatteryHeatingScheduleCommand(
    PayloadConvertingCommandHandler[BatteryHeatingScheduleCommandPayload]
):
    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.DRIVETRAIN_BATTERY_HEATING_SCHEDULE_SET

    @property
    @override
    def state_topic(self) -> str:
        return mqtt_topics.DRIVETRAIN_BATTERY_HEATING_SCHEDULE

    @property
    @override
    def current_state(self) -> dict[str, Any] | None:
        start_time = self.vehicle_state.scheduled_battery_heating_start
        if start_time is None:
            return None
        return {
            "startTime": start_time.strftime("%H:%M"),
            "mode": "on"
            if self.vehicle_state.scheduled_battery_heating_enabled
            else "off",
        }

    @override
    def expected_state(self, raw_payload: str) -> dict[str, Any] | None:
        try:
            parsed = self.convert_payload(raw_payload)
        except (ValueError, KeyError, json.JSONDecodeError):
            return None
        return {
            "startTime": parsed.start_time.strftime("%H:%M"),
            "mode": "on" if parsed.enable else "off",
        }

    @staticmethod
    @override
    def convert_payload(payload: str) -> BatteryHeatingScheduleCommandPayload:
        payload_json = json.loads(payload.strip())
        return BatteryHeatingScheduleCommandPayload.from_json(payload_json)

    @override
    async def handle_typed_payload(
        self, payload: BatteryHeatingScheduleCommandPayload
    ) -> CommandProcessingResult:
        start_time = payload.start_time
        should_enable = payload.enable
        changed = self.vehicle_state.update_scheduled_battery_heating(
            start_time, should_enable
        )
        if changed:
            if should_enable:
                LOG.info(f"Setting battery heating schedule to {start_time}")
                await self.saic_api.enable_schedule_battery_heating(
                    self.vin,
                    start_time=start_time,
                    tz=self.vehicle_state.user_timezone,
                )
            else:
                LOG.info("Disabling battery heating schedule")
                await self.saic_api.disable_schedule_battery_heating(self.vin)
        else:
            LOG.info("Battery heating schedule not changed")
        return RESULT_REFRESH_ONLY
