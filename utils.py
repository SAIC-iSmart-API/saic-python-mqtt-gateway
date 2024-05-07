from datetime import datetime, timezone, timedelta

from saic_ismart_client_ng.api.schema import GpsStatus
from saic_ismart_client_ng.api.vehicle import VehicleStatusResp


def value_in_range(value, min_incl, max_excl) -> bool:
    return value is not None and min_incl <= value < max_excl


def is_valid_temperature(value) -> bool:
    return value_in_range(value, -127, 127) and value != 87


def get_update_timestamp(vehicle_status: VehicleStatusResp) -> datetime:
    vehicle_status_time = datetime.fromtimestamp(vehicle_status.statusTime or 0, tz=timezone.utc)
    now_time = datetime.now(tz=timezone.utc)
    # Do not use GPS data if it is not available
    if vehicle_status.gpsPosition and vehicle_status.gpsPosition.gps_status_decoded in [GpsStatus.FIX_2D,
                                                                                        GpsStatus.FIX_3d]:
        gps_time = datetime.fromtimestamp(vehicle_status.gpsPosition.timeStamp or 0, tz=timezone.utc)
    else:
        gps_time = datetime.fromtimestamp(0, tz=timezone.utc)
    vehicle_status_drift = abs(now_time - vehicle_status_time)
    gps_time_drift = abs(now_time - gps_time)
    reference_drift = min(gps_time_drift, vehicle_status_drift)
    reference_time = gps_time if gps_time_drift < vehicle_status_drift else vehicle_status_time
    if reference_drift < timedelta(minutes=15):
        return reference_time
    else:
        return now_time
