import json
import logging
from abc import ABC
from typing import Any, Tuple, Optional

import httpx
from saic_ismart_client_ng.api.schema import GpsPosition, GpsStatus
from saic_ismart_client_ng.api.vehicle import VehicleStatusResp
from saic_ismart_client_ng.api.vehicle.schema import BasicVehicleStatus
from saic_ismart_client_ng.api.vehicle_charging import ChrgMgmtDataResp
from saic_ismart_client_ng.api.vehicle_charging.schema import RvsChargeStatus

from integrations import IntegrationException
from utils import value_in_range, get_update_timestamp

LOG = logging.getLogger(__name__)


class OsmAndApiException(IntegrationException):
    def __init__(self, msg: str):
        super().__init__(__name__, msg)


class OsmAndApiListener(ABC):
    async def on_request(self, path: str, body: Optional[str] = None, headers: Optional[dict] = None):
        pass

    async def on_response(self, path: str, body: Optional[str] = None, headers: Optional[dict] = None):
        pass


class OsmAndApi:
    def __init__(self, *, server_uri: str, device_id: str, listener: Optional[OsmAndApiListener] = None) -> None:
        self.__device_id = device_id
        self.__listener = listener
        self.__server_uri = server_uri
        self.client = httpx.AsyncClient(
            event_hooks={
                "request": [self.invoke_request_listener],
                "response": [self.invoke_response_listener]
            }
        )

    async def update_osmand(self, vehicle_status: VehicleStatusResp, charge_info: ChrgMgmtDataResp | None) \
            -> Tuple[bool, Any | None]:

        charge_mgmt_data = None if charge_info is None else charge_info.chrgMgmtData
        charge_status = None if charge_info is None else charge_info.rvsChargeStatus

        if (
                self.__device_id is not None
                and self.__server_uri is not None
                and vehicle_status is not None
        ):
            # Request
            data = {
                'id': self.__device_id,
                # Guess the timestamp from either the API, GPS info or current machine time
                'timestamp': int(get_update_timestamp(vehicle_status).timestamp()),
                'is_charging': vehicle_status.is_charging,
                'is_parked': vehicle_status.is_parked,
            }

            if vehicle_status.is_parked:
                data.update({
                    # We assume the vehicle is stationary, we will update it later from GPS if available
                    'speed': 0.0,
                })

            basic_vehicle_status = vehicle_status.basicVehicleStatus
            if basic_vehicle_status is not None:
                data.update(self.__extract_basic_vehicle_status(basic_vehicle_status))

            gps_position = vehicle_status.gpsPosition
            if gps_position is not None:
                data.update(self.__extract_gps_position(gps_position))

            if charge_mgmt_data is not None:
                data.update({
                    'soc': (charge_mgmt_data.bmsPackSOCDsp / 10.0)
                })

                # Skip invalid current values reported by the API
                is_valid_current = (
                        charge_mgmt_data.bmsPackCrntV != 1
                        and value_in_range(charge_mgmt_data.bmsPackCrnt, 0, 65535)
                )
                if is_valid_current:
                    data.update({
                        'power': charge_mgmt_data.decoded_power,
                        'voltage': charge_mgmt_data.decoded_voltage,
                        'current': charge_mgmt_data.decoded_current
                    })

            # Extract electric range if available
            data.update(self.__extract_electric_range(basic_vehicle_status, charge_status))

            try:
                response = await self.client.post(url=self.__server_uri, params=data)
                await response.aread()
                return True, response.text
            except httpx.ConnectError as ece:
                raise OsmAndApiException(f'Connection error: {ece}')
            except httpx.TimeoutException as et:
                raise OsmAndApiException(f'Timeout error {et}')
            except httpx.RequestError as e:
                raise OsmAndApiException(f'{e}')
            except httpx.HTTPError as ehttp:
                raise OsmAndApiException(f'HTTP error {ehttp}')
        else:
            return False, 'OsmAnd request skipped because of missing configuration'

    @staticmethod
    def __extract_basic_vehicle_status(basic_vehicle_status: BasicVehicleStatus) -> dict:
        data = {}

        exterior_temperature = basic_vehicle_status.exteriorTemperature
        if exterior_temperature is not None and value_in_range(exterior_temperature, -127, 127):
            data['ext_temp'] = exterior_temperature
        mileage = basic_vehicle_status.mileage
        # Skip invalid range readings
        if mileage is not None and value_in_range(mileage, 1, 2147483647):
            data['odometer'] = 100 * mileage

        return data

    @staticmethod
    def __extract_gps_position(gps_position: GpsPosition) -> dict:
        data = {}

        # Do not use GPS data if it is not available
        if gps_position.gps_status_decoded not in [GpsStatus.FIX_2D, GpsStatus.FIX_3d]:
            return data

        way_point = gps_position.wayPoint
        if way_point is None:
            return data

        speed = way_point.speed
        if value_in_range(speed, -999, 4500):
            data['speed'] = speed / 10

        heading = way_point.heading
        if value_in_range(heading, 0, 360):
            data['heading'] = heading

        position = way_point.position
        if position is None:
            return data

        altitude = position.altitude
        if value_in_range(altitude, -500, 8900):
            data['altitude'] = altitude

        lat_degrees = position.latitude / 1000000.0
        lon_degrees = position.longitude / 1000000.0

        if (
                abs(lat_degrees) <= 90
                and abs(lon_degrees) <= 180
        ):
            data.update({
                'hdop': way_point.hdop,
                'lat': lat_degrees,
                'lon': lon_degrees,
            })

        return data

    def __extract_electric_range(
            self,
            basic_vehicle_status: BasicVehicleStatus | None,
            charge_status: RvsChargeStatus | None
    ) -> dict:

        data = {}

        range_elec_vehicle = 0.0
        if basic_vehicle_status is not None:
            range_elec_vehicle = self.__parse_electric_range(raw_value=basic_vehicle_status.fuelRangeElec)

        range_elec_bms = 0.0
        if charge_status is not None:
            range_elec_bms = self.__parse_electric_range(raw_value=charge_status.fuelRangeElec)

        range_elec = max(range_elec_vehicle, range_elec_bms)
        if range_elec > 0:
            data['est_battery_range'] = range_elec

        return data

    @staticmethod
    def __parse_electric_range(raw_value) -> float:
        if value_in_range(raw_value, 1, 65535):
            return float(raw_value) / 10.0
        return 0.0

    async def invoke_request_listener(self, request: httpx.Request):
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
                path=str(request.url).replace(self.__server_uri, "/"),
                body=body,
                headers=dict(request.headers),
            )
        except Exception as e:
            LOG.warning(f"Error invoking request listener: {e}", exc_info=e)

    async def invoke_response_listener(self, response: httpx.Response):
        if not self.__listener:
            return
        try:
            body = await response.aread()
            if body:
                try:
                    body = body.decode("utf-8")
                except Exception as e:
                    LOG.warning(f"Error decoding request content: {e}")

            await self.__listener.on_response(
                path=str(response.url).replace(self.__server_uri, "/"),
                body=body,
                headers=dict(response.headers),
            )
        except Exception as e:
            LOG.warning(f"Error invoking request listener: {e}", exc_info=e)
