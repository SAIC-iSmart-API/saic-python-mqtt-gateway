from __future__ import annotations

from datetime import UTC, datetime, timedelta
from importlib.metadata import PackageNotFoundError, version
import logging
import os
import re
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from saic_ismart_client_ng.api.schema import GpsStatus

if TYPE_CHECKING:
    from saic_ismart_client_ng.api.vehicle import VehicleStatusResp

LOG = logging.getLogger(__name__)


def parse_timezone(tz_str: str) -> ZoneInfo:
    """Parse a timezone string into a :class:`ZoneInfo`.

    Accepts both IANA names (``Australia/Sydney``) and the ``GMT+HH:MM``
    offset format returned by the SAIC API.
    """
    try:
        return ZoneInfo(tz_str)
    except (KeyError, ModuleNotFoundError):
        pass

    # Handle GMT+HH:MM / GMT-HH:MM format from the SAIC API.
    # POSIX Etc/GMT zones use inverted signs: GMT+01:00 → Etc/GMT-1
    m = re.fullmatch(r"GMT([+-])(\d{2}):(\d{2})", tz_str)
    if m:
        sign, hours, minutes = m.group(1), int(m.group(2)), int(m.group(3))
        if minutes != 0:
            LOG.warning(
                "Timezone %s has non-zero minutes, rounding to whole hour", tz_str
            )
        posix_sign = "-" if sign == "+" else "+"
        return ZoneInfo(f"Etc/GMT{posix_sign}{hours}")

    msg = f"Unrecognized timezone format: {tz_str}"
    raise ValueError(msg)


def value_in_range[Numeric: (int, float)](
    value: Numeric,
    min_value: Numeric,
    max_value: Numeric,
    is_max_excl: bool = True,
) -> bool:
    if value is None:
        return False
    if is_max_excl:
        return min_value <= value < max_value
    return min_value <= value <= max_value


def is_valid_temperature(value: int) -> bool:
    return value_in_range(value, -127, 127) and value != 87


def get_update_timestamp(vehicle_status: VehicleStatusResp) -> datetime:
    vehicle_status_time = datetime.fromtimestamp(vehicle_status.statusTime or 0, tz=UTC)
    now_time = datetime.now(tz=UTC)
    # Do not use GPS data if it is not available
    if vehicle_status.gpsPosition and vehicle_status.gpsPosition.gps_status_decoded in [
        GpsStatus.FIX_2D,
        GpsStatus.FIX_3d,
    ]:
        gps_time = datetime.fromtimestamp(
            vehicle_status.gpsPosition.timeStamp or 0, tz=UTC
        )
    else:
        gps_time = datetime.fromtimestamp(0, tz=UTC)
    vehicle_status_drift = abs(now_time - vehicle_status_time)
    gps_time_drift = abs(now_time - gps_time)
    reference_drift = min(gps_time_drift, vehicle_status_drift)
    reference_time = (
        gps_time if gps_time_drift < vehicle_status_drift else vehicle_status_time
    )
    if reference_drift < timedelta(minutes=15):
        return reference_time
    return now_time


def get_gateway_version() -> str:
    try:
        return version("saic-python-mqtt-gateway")
    except PackageNotFoundError:
        return os.environ.get("RELEASE_VERSION", "unknown")


def ensure_datetime_aware(dt: datetime) -> datetime:
    """Return *dt* with UTC tzinfo if it is naive, otherwise unchanged."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def datetime_to_str(dt: datetime) -> str:
    return datetime.astimezone(dt, tz=UTC).isoformat()


def int_to_bool(value: int) -> bool:
    return value > 0


def to_remote_climate(rmt_htd_rr_wnd_st: int) -> str:
    match rmt_htd_rr_wnd_st:
        case 0:
            return "off"
        case 1:
            return "blowingonly"
        case 2:
            return "on"
        case 5:
            return "front"

    return f"unknown ({rmt_htd_rr_wnd_st})"
