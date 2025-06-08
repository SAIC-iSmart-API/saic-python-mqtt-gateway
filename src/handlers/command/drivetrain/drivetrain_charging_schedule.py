from __future__ import annotations

from dataclasses import dataclass
from datetime import time
import json
import logging
from typing import TYPE_CHECKING, Any, override

from saic_ismart_client_ng.api.vehicle_charging import ScheduledChargingMode

from handlers.command.base import PayloadConvertingCommandHandler
import mqtt_topics

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

    @staticmethod
    @override
    def convert_payload(payload: str) -> ChargingScheduleCommandPayload:
        payload_json = json.loads(payload.strip())
        return ChargingScheduleCommandPayload.from_json(payload_json)

    @override
    async def handle_typed_payload(
        self, payload: ChargingScheduleCommandPayload
    ) -> bool:
        LOG.info("Setting charging schedule to %s", str(payload))
        await self.saic_api.set_schedule_charging(
            self.vin,
            start_time=payload.start_time,
            end_time=payload.end_time,
            mode=payload.mode,
        )
        self.vehicle_state.update_scheduled_charging(payload.start_time, payload.mode)
        return True
