from __future__ import annotations

from abc import ABC, abstractmethod
import json
import logging
from typing import TYPE_CHECKING, Any

import httpx
from saic_ismart_client_ng.api.schema import GpsPosition, GpsStatus

from integrations import IntegrationException
from utils import get_update_timestamp, value_in_range

if TYPE_CHECKING:
    from saic_ismart_client_ng.api.vehicle import VehicleStatusResp
    from saic_ismart_client_ng.api.vehicle.schema import BasicVehicleStatus
    from saic_ismart_client_ng.api.vehicle_charging import ChrgMgmtDataResp
    from saic_ismart_client_ng.api.vehicle_charging.schema import RvsChargeStatus

LOG = logging.getLogger(__name__)


class AbrpApiException(IntegrationException):
    def __init__(self, msg: str) -> None:
        super().__init__(__name__, msg)


class AbrpApiListener(ABC):
    @abstractmethod
    async def on_request(
        self,
        path: str,
        body: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        pass

    @abstractmethod
    async def on_response(
        self,
        path: str,
        body: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        pass


class AbrpApi:
    def __init__(
        self,
        abrp_api_key: str | None,
        abrp_user_token: str | None,
        listener: AbrpApiListener | None = None,
    ) -> None:
        self.abrp_api_key = abrp_api_key
        self.abrp_user_token = abrp_user_token
        self.__listener = listener
        self.__base_uri = "https://api.iternio.com/1/"
        self.client = httpx.AsyncClient(
            event_hooks={
                "request": [self.invoke_request_listener],
                "response": [self.invoke_response_listener],
            }
        )

    async def update_abrp(
        self,
        vehicle_status: VehicleStatusResp | None,
        charge_info: ChrgMgmtDataResp | None,
    ) -> tuple[bool, str]:
        charge_mgmt_data = None if charge_info is None else charge_info.chrgMgmtData
        charge_status = None if charge_info is None else charge_info.rvsChargeStatus

        if (
            self.abrp_api_key is not None
            and self.abrp_user_token is not None
            and vehicle_status is not None
            and charge_mgmt_data is not None
        ):
            # Request
            tlm_send_url = f"{self.__base_uri}tlm/send"
            data: dict[str, Any] = {
                # Guess the timestamp from either the API, GPS info or current machine time
                "utc": int(get_update_timestamp(vehicle_status).timestamp()),
            }
            if (soc := charge_mgmt_data.bmsPackSOCDsp) is not None:
                data.update(
                    {
                        "soc": (soc / 10.0),
                    }
                )

            # Skip invalid current values reported by the API
            decoded_current = charge_mgmt_data.decoded_current
            is_valid_current = (
                charge_mgmt_data.bmsPackCrntV != 1
                and (raw_current := charge_mgmt_data.bmsPackCrnt) is not None
                and value_in_range(raw_current, 0, 65535)
                and decoded_current is not None
            )
            if is_valid_current:
                is_charging = (
                    charge_status is not None
                    and charge_status.chargingGunState
                    and decoded_current is not None
                    and decoded_current < 0.0
                )
                data.update(
                    {
                        "power": charge_mgmt_data.decoded_power,
                        "voltage": charge_mgmt_data.decoded_voltage,
                        "current": decoded_current,
                        "is_charging": is_charging,
                    }
                )

            basic_vehicle_status = vehicle_status.basicVehicleStatus
            if basic_vehicle_status is not None:
                data.update(self.__extract_basic_vehicle_status(basic_vehicle_status))

            # Extract electric range if available
            data.update(
                self.__extract_electric_range(basic_vehicle_status, charge_status)
            )

            gps_position = vehicle_status.gpsPosition
            if gps_position is not None:
                data.update(self.__extract_gps_position(gps_position))

            headers = {"Authorization": f"APIKEY {self.abrp_api_key}"}

            try:
                response = await self.client.post(
                    url=tlm_send_url,
                    headers=headers,
                    params={"token": self.abrp_user_token, "tlm": json.dumps(data)},
                )
                await response.aread()
                return True, response.text
            except httpx.ConnectError as ece:
                msg = f"Connection error: {ece}"
                raise AbrpApiException(msg) from ece
            except httpx.TimeoutException as et:
                msg = f"Timeout error {et}"
                raise AbrpApiException(msg) from et
            except httpx.RequestError as e:
                msg = f"{e}"
                raise AbrpApiException(msg) from e
            except httpx.HTTPError as ehttp:
                msg = f"HTTP error {ehttp}"
                raise AbrpApiException(msg) from ehttp
        else:
            return False, "ABRP request skipped because of missing configuration"

    @staticmethod
    def __extract_basic_vehicle_status(
        basic_vehicle_status: BasicVehicleStatus,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "is_parked": basic_vehicle_status.is_parked,
        }

        exterior_temperature = basic_vehicle_status.exteriorTemperature
        if exterior_temperature is not None and value_in_range(
            exterior_temperature, -127, 127
        ):
            data["ext_temp"] = exterior_temperature
        mileage = basic_vehicle_status.mileage
        # Skip invalid range readings
        if mileage is not None and value_in_range(mileage, 1, 2147483647):
            # Data must be reported in km
            data["odometer"] = mileage / 10.0

        if basic_vehicle_status.is_parked:
            # We assume the vehicle is stationary, we will update it later from GPS if available
            data["speed"] = 0.0

        return data

    @staticmethod
    def __extract_gps_position(gps_position: GpsPosition) -> dict[str, Any]:
        data: dict[str, Any] = {}

        # Do not use GPS data if it is not available
        if gps_position.gps_status_decoded not in [GpsStatus.FIX_2D, GpsStatus.FIX_3d]:
            return data

        way_point = gps_position.wayPoint
        if way_point is None:
            return data

        speed = way_point.speed
        if speed is not None and value_in_range(speed, -999, 4500):
            data["speed"] = speed / 10

        heading = way_point.heading
        if heading is not None and value_in_range(heading, 0, 360):
            data["heading"] = heading

        position = way_point.position
        if position is None:
            return data

        altitude = position.altitude
        if altitude is not None and value_in_range(altitude, -500, 8900):
            data["elevation"] = altitude

        if (raw_lat := position.latitude) is not None and (
            raw_lon := position.longitude
        ) is not None:
            lat_degrees = raw_lat / 1000000.0
            lon_degrees = raw_lon / 1000000.0

            if abs(lat_degrees) <= 90 and abs(lon_degrees) <= 180:
                data.update(
                    {
                        "lat": lat_degrees,
                        "lon": lon_degrees,
                    }
                )

        return data

    def __extract_electric_range(
        self,
        basic_vehicle_status: BasicVehicleStatus | None,
        charge_status: RvsChargeStatus | None,
    ) -> dict[str, Any]:
        data = {}

        range_elec_vehicle = 0.0
        if (
            basic_vehicle_status
            and (fuel_range := basic_vehicle_status.fuelRangeElec) is not None
        ):
            range_elec_vehicle = self.__parse_electric_range(raw_value=fuel_range)

        range_elec_bms = 0.0
        if charge_status and (fuel_range := charge_status.fuelRangeElec) is not None:
            range_elec_bms = self.__parse_electric_range(raw_value=fuel_range)

        range_elec = max(range_elec_vehicle, range_elec_bms)
        if range_elec > 0:
            data["est_battery_range"] = range_elec

        return data

    @staticmethod
    def __parse_electric_range(raw_value: int) -> float:
        if value_in_range(raw_value, 1, 20460):
            return float(raw_value) / 10.0
        return 0.0

    async def invoke_request_listener(self, request: httpx.Request) -> None:
        if not self.__listener:
            return
        try:
            body = None
            if request.content:
                try:
                    body = request.content.decode("utf-8")
                except Exception as e:
                    LOG.warning(f"Error decoding request content: {e}")

            await self.__listener.on_request(
                path=str(request.url).replace(self.__base_uri, "/"),
                body=body,
                headers=dict(request.headers),
            )
        except Exception as e:
            LOG.warning(f"Error invoking request listener: {e}", exc_info=e)

    async def invoke_response_listener(self, response: httpx.Response) -> None:
        if not self.__listener:
            return
        try:
            body = await response.aread()
            decoded_body: str | None = None
            if body:
                try:
                    decoded_body = body.decode("utf-8")
                except Exception as e:
                    LOG.warning(f"Error decoding request content: {e}")

            await self.__listener.on_response(
                path=str(response.url).replace(self.__base_uri, "/"),
                body=decoded_body,
                headers=dict(response.headers),
            )
        except Exception as e:
            LOG.warning(f"Error invoking request listener: {e}", exc_info=e)
