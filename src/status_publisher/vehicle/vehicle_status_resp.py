from __future__ import annotations

from dataclasses import dataclass
import datetime
from typing import TYPE_CHECKING, Final

from exceptions import MqttGatewayException
import mqtt_topics
from status_publisher import VehicleDataPublisher
from status_publisher.vehicle.basic_vehicle_status import (
    BasicVehicleStatusProcessingResult,
    BasicVehicleStatusPublisher,
)
from status_publisher.vehicle.gps_position import (
    GpsPositionProcessingResult,
    GpsPositionPublisher,
)

if TYPE_CHECKING:
    from saic_ismart_client_ng.api.schema import GpsPosition
    from saic_ismart_client_ng.api.vehicle import BasicVehicleStatus, VehicleStatusResp

    from publisher.core import Publisher
    from vehicle_info import VehicleInfo


@dataclass(kw_only=True, frozen=True)
class VehicleStatusRespProcessingResult:
    hv_battery_active_from_car: bool
    remote_ac_running: bool
    remote_heated_seats_front_right_level: int | None
    remote_heated_seats_front_left_level: int | None
    fuel_range_elec: int | None
    raw_soc: int | None


class VehicleStatusRespPublisher(VehicleDataPublisher):
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

    def on_vehicle_status_resp(
        self, vehicle_status: VehicleStatusResp
    ) -> VehicleStatusRespProcessingResult:
        vehicle_status_time = datetime.datetime.fromtimestamp(
            vehicle_status.statusTime or 0, tz=datetime.UTC
        )
        now_time = datetime.datetime.now(tz=datetime.UTC)
        vehicle_status_drift = abs(now_time - vehicle_status_time)

        if vehicle_status_drift > datetime.timedelta(minutes=15):
            msg = f"Vehicle status time drifted more than 15 minutes from current time: {vehicle_status_drift}. Server reported {vehicle_status_time}"
            raise MqttGatewayException(msg)

        basic_vehicle_status = vehicle_status.basicVehicleStatus
        if basic_vehicle_status:
            return self.__on_basic_vehicle_status(
                basic_vehicle_status, vehicle_status.gpsPosition
            )
        msg = f"Missing basic vehicle status data: {basic_vehicle_status}. We'll mark this poll as failed"
        raise MqttGatewayException(msg)

    def __on_basic_vehicle_status(
        self, basic_vehicle_status: BasicVehicleStatus, gps_position: GpsPosition | None
    ) -> VehicleStatusRespProcessingResult:
        basic_vehicle_status_result = (
            self.__basic_vehicle_status_publisher.on_basic_vehicle_status(
                basic_vehicle_status
            )
        )

        if gps_position:
            self.__on_gps_position(basic_vehicle_status_result, gps_position)

        self._publish(
            topic=mqtt_topics.REFRESH_LAST_VEHICLE_STATE,
            value=datetime.datetime.now(),
        )

        return VehicleStatusRespProcessingResult(
            hv_battery_active_from_car=basic_vehicle_status_result.hv_battery_active_from_car,
            remote_ac_running=basic_vehicle_status_result.remote_ac_running,
            remote_heated_seats_front_left_level=basic_vehicle_status_result.remote_heated_seats_front_left_level,
            remote_heated_seats_front_right_level=basic_vehicle_status_result.remote_heated_seats_front_right_level,
            raw_soc=basic_vehicle_status_result.raw_soc,
            fuel_range_elec=basic_vehicle_status_result.fuel_rage_elec,
        )

    def __on_gps_position(
        self,
        basic_vehicle_status_result: BasicVehicleStatusProcessingResult,
        gps_position: GpsPosition,
    ) -> None:
        gps_position_result = self.__gps_position_publisher.on_gps_position(
            gps_position
        )
        self.__fuse_data(basic_vehicle_status_result, gps_position_result)

    def __fuse_data(
        self,
        basic_vehicle_status_result: BasicVehicleStatusProcessingResult,
        gps_position_result: GpsPositionProcessingResult,
    ) -> None:
        gps_speed = gps_position_result.speed
        is_parked = basic_vehicle_status_result.is_parked
        if gps_speed is not None and is_parked:
            gps_speed = 0.0

        self._publish(topic=mqtt_topics.LOCATION_SPEED, value=gps_speed)
