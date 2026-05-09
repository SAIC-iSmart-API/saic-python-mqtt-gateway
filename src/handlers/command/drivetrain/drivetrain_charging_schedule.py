from __future__ import annotations

from dataclasses import dataclass
from datetime import time
import json
import logging
from typing import TYPE_CHECKING, Any, override

from saic_ismart_client_ng.api.vehicle_charging import ScheduledChargingMode

from handlers.command.base import (
    RESULT_DO_NOTHING,
    RESULT_REFRESH_ONLY,
    CommandProcessingResult,
    PayloadConvertingCommandHandler,
)
import mqtt_topics
from status_publisher.charge.chrg_mgmt_data import ScheduledCharging

if TYPE_CHECKING:
    from collections.abc import Mapping

LOG = logging.getLogger(__name__)


@dataclass
class ChargingScheduleCommandPayload:
    start_time: time
    end_time: time
    mode: ScheduledChargingMode

    @staticmethod
    def from_json(payload_json: Mapping[str, Any]) -> ChargingScheduleCommandPayload:
        return ChargingScheduleCommandPayload(
            time.fromisoformat(payload_json["startTime"]),
            time.fromisoformat(payload_json["endTime"]),
            ScheduledChargingMode[payload_json["mode"].upper()],
        )


class DrivetrainChargingScheduleCommand(
    PayloadConvertingCommandHandler[ChargingScheduleCommandPayload]
):
    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.DRIVETRAIN_CHARGING_SCHEDULE_SET

    @property
    @override
    def state_topic(self) -> str:
        return mqtt_topics.DRIVETRAIN_CHARGING_SCHEDULE

    @property
    @override
    def current_state(self) -> dict[str, Any] | None:
        schedule = self.vehicle_state.scheduled_charging
        if schedule is None:
            return None
        return {
            "startTime": schedule.start_time.strftime("%H:%M"),
            "endTime": schedule.end_time.strftime("%H:%M"),
            "mode": schedule.mode.name,
        }

    @override
    def expected_state(self, raw_payload: str) -> dict[str, Any] | None:
        try:
            parsed = self.convert_payload(raw_payload)
        except (ValueError, KeyError, json.JSONDecodeError):
            return None
        return {
            "startTime": parsed.start_time.strftime("%H:%M"),
            "endTime": parsed.end_time.strftime("%H:%M"),
            "mode": parsed.mode.name,
        }

    @staticmethod
    @override
    def convert_payload(payload: str) -> ChargingScheduleCommandPayload:
        payload_json = json.loads(payload.strip())
        return ChargingScheduleCommandPayload.from_json(payload_json)

    @override
    async def handle_typed_payload(
        self, payload: ChargingScheduleCommandPayload
    ) -> CommandProcessingResult:
        if (
            payload.mode == ScheduledChargingMode.UNTIL_CONFIGURED_SOC
            and not self.vehicle_state.vehicle.supports_target_soc
        ):
            LOG.warning(
                "Ignoring UNTIL_CONFIGURED_SOC charging schedule: "
                "vehicle does not support target SoC"
            )
            return RESULT_DO_NOTHING
        LOG.info("Setting charging schedule to %s", str(payload))
        await self.saic_api.set_schedule_charging(
            self.vin,
            start_time=payload.start_time,
            end_time=payload.end_time,
            mode=payload.mode,
        )
        self.vehicle_state.update_scheduled_charging(
            ScheduledCharging(
                start_time=payload.start_time,
                end_time=payload.end_time,
                mode=payload.mode,
            )
        )
        return RESULT_REFRESH_ONLY
