from __future__ import annotations

from dataclasses import dataclass
import datetime
from typing import TYPE_CHECKING, Final, override

from saic_ismart_client_ng.api.vehicle import (
    BasicVehicleStatus,
    VehicleStatusCacheResp,
)

from status_publisher import VehicleDataPublisher
from status_publisher.vehicle.basic_vehicle_status import BasicVehicleStatusPublisher
from status_publisher.vehicle.gps_position import GpsPositionPublisher
from status_publisher.vehicle.vehicle_status_resp import (
    VehicleStatusRespProcessingResult,
)

if TYPE_CHECKING:
    from publisher.core import Publisher
    from vehicle_info import VehicleInfo

_INVALID_TIMESTAMPS: Final = frozenset({0, 2147483647})
_INVALID_RAW_VALUES: Final = frozenset({0, 65535})
_MAX_FUTURE_DRIFT: Final = datetime.timedelta(minutes=15)


@dataclass(kw_only=True, frozen=True)
class CachedStatusState:
    """What the gateway already knows, used to judge a cached status."""

    last_live_status_time: int | None
    last_cached_status_time: int | None
    last_known_mileage: int | None


@dataclass(kw_only=True, frozen=True)
class CachedStatusProcessingResult:
    status_time: int
    result: VehicleStatusRespProcessingResult


def check_cached_status(
    cached: VehicleStatusCacheResp,
    state: CachedStatusState,
    *,
    now: datetime.datetime | None = None,
) -> str | None:
    """Return why the cached status must not be used, or None if it can be.

    The cache sometimes holds nonsense (battery 0%, huge odometer), so a
    response with any implausible core value is dropped as a whole.
    """
    basic = cached.basicVehicleStatus
    if basic is None:
        return "missing basicVehicleStatus"
    return _check_status_time(
        cached.statusTime, state, now or datetime.datetime.now(tz=datetime.UTC)
    ) or _check_values(basic, state)


def _check_status_time(
    status_time: int | None, state: CachedStatusState, now: datetime.datetime
) -> str | None:
    if status_time is None or status_time in _INVALID_TIMESTAMPS:
        return f"invalid statusTime {status_time}"
    status_datetime = datetime.datetime.fromtimestamp(status_time, tz=datetime.UTC)
    if status_datetime > now + _MAX_FUTURE_DRIFT:
        return f"statusTime {status_time} is in the future"
    if (
        state.last_cached_status_time is not None
        and status_time <= state.last_cached_status_time
    ):
        return "statusTime unchanged since the last cached read"
    if (
        state.last_live_status_time is not None
        and status_time <= state.last_live_status_time
    ):
        return "not newer than the last live status"
    return None


def _check_values(basic: BasicVehicleStatus, state: CachedStatusState) -> str | None:
    mileage = basic.mileage
    if mileage is None or mileage in _INVALID_RAW_VALUES or mileage >= 2147483647:
        return f"invalid mileage {mileage}"
    if state.last_known_mileage is not None and mileage < state.last_known_mileage:
        return f"mileage went down ({mileage} < {state.last_known_mileage})"
    soc = basic.extendedData1
    if soc is not None and (soc in _INVALID_RAW_VALUES or soc > 100):
        return f"invalid SoC {soc}"
    electric_range = basic.fuelRangeElec
    if electric_range is not None and electric_range in _INVALID_RAW_VALUES:
        return f"invalid electric range {electric_range}"
    return None


class VehicleStatusCachePublisher(
    VehicleDataPublisher[VehicleStatusCacheResp, CachedStatusProcessingResult]
):
    """Publishes a cached status that already passed `check_cached_status`.

    The caller must not use `hv_battery_active_from_car` or `remote_ac_running`
    from the result: the cache is no proof the car is awake or asleep.
    """

    def __init__(
        self, vin: VehicleInfo, publisher: Publisher, mqtt_vehicle_prefix: str
    ) -> None:
        super().__init__(vin, publisher, mqtt_vehicle_prefix)
        self.__gps_position_publisher: Final[GpsPositionPublisher] = (
            GpsPositionPublisher(vin, publisher, mqtt_vehicle_prefix)
        )
        self.__basic_vehicle_status_publisher: Final[BasicVehicleStatusPublisher] = (
            BasicVehicleStatusPublisher(vin, publisher, mqtt_vehicle_prefix)
        )

    @override
    def publish(self, data: VehicleStatusCacheResp) -> CachedStatusProcessingResult:
        basic = data.basicVehicleStatus
        status_time = data.statusTime
        if basic is None or status_time is None:
            msg = "Cached status must be validated before publishing"
            raise ValueError(msg)

        basic_result = self.__basic_vehicle_status_publisher.publish(basic)
        if data.gpsPosition:
            self.__gps_position_publisher.publish(data.gpsPosition)

        return CachedStatusProcessingResult(
            status_time=status_time,
            result=VehicleStatusRespProcessingResult(
                hv_battery_active_from_car=basic_result.hv_battery_active_from_car,
                remote_ac_running=basic_result.remote_ac_running,
                remote_heated_seats_front_left_level=basic_result.remote_heated_seats_front_left_level,
                remote_heated_seats_front_right_level=basic_result.remote_heated_seats_front_right_level,
                fuel_range_elec=basic_result.fuel_rage_elec,
                raw_soc=basic_result.raw_soc,
                raw_mileage=basic_result.raw_mileage,
            ),
        )
