from __future__ import annotations

from enum import Enum
from typing import cast, override

from saic_ismart_client_ng.api.vehicle import (
    RvcParams,
    RvcParamsId,
    RvcReqType,
    VehicleControlReq,
)

from handlers.command.base import (
    RESULT_REFRESH_AND_CLEAR,
    BooleanCommandHandler,
    CommandProcessingResult,
)
import mqtt_topics


class _SteeringWheelProtocol(Enum):
    # The 0.10 client constructors use .value, but its enums lack these entries.
    # https://github.com/townsmcp/saic-python-client-ng/blob/master/src/saic_ismart_client_ng/api/vehicle/climate/__init__.py
    REQUEST_TYPE = "8"
    PARAMETER_ID = 24


class ClimateSteeringWheelHeatCommand(BooleanCommandHandler[None]):
    @classmethod
    @override
    def topic(cls) -> str:
        return mqtt_topics.CLIMATE_STEERING_WHEEL_HEAT_SET

    @override
    async def handle_true(self) -> None:
        await self._control_heat(enable=True)

    @override
    async def handle_false(self) -> None:
        await self._control_heat(enable=False)

    async def _control_heat(self, *, enable: bool) -> None:
        request = VehicleControlReq(
            rvc_req_type=cast("RvcReqType", _SteeringWheelProtocol.REQUEST_TYPE),
            rvc_params=[
                RvcParams(
                    cast("RvcParamsId", _SteeringWheelProtocol.PARAMETER_ID),
                    b"\x01" if enable else b"\x00",
                ),
            ],
            vin=self.vin,
        )
        # This command has no PARAMS_MAX marker. The client hashes the VIN and
        # handles authentication, response validation and command polling.
        await self.saic_api.send_vehicle_control_command(request, self.vin)

    @override
    async def _get_action_result(self, _action_result: None) -> CommandProcessingResult:
        return RESULT_REFRESH_AND_CLEAR
