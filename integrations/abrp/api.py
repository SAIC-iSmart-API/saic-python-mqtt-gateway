import json
import logging
import time
from abc import ABC
from typing import Any, Tuple, Optional

import httpx
from saic_ismart_client_ng.api.schema import GpsPosition, GpsStatus
from saic_ismart_client_ng.api.vehicle import VehicleStatusResp
from saic_ismart_client_ng.api.vehicle.schema import BasicVehicleStatus
from saic_ismart_client_ng.api.vehicle_charging import ChrgMgmtDataResp

from utils import value_in_range

LOG = logging.getLogger(__name__)


class AbrpApiException(Exception):
    def __init__(self, msg: str):
        self.message = msg

    def __str__(self):
        return self.message


class AbrpApiListener(ABC):
    async def on_request(self, path: str, body: Optional[str] = None, headers: Optional[dict] = None):
        pass

    async def on_response(self, path: str, body: Optional[str] = None, headers: Optional[dict] = None):
        pass


class AbrpApi:
    def __init__(self, abrp_api_key: str, abrp_user_token: str, listener: Optional[AbrpApiListener] = None) -> None:
        self.abrp_api_key = abrp_api_key
        self.abrp_user_token = abrp_user_token
        self.__listener = listener
        self.__base_uri = 'https://api.iternio.com/1/'
        self.client = httpx.AsyncClient(
            event_hooks={
                "request": [self.invoke_request_listener],
                "response": [self.invoke_response_listener]
            }
        )

    async def update_abrp(self, vehicle_status: VehicleStatusResp, charge_info: ChrgMgmtDataResp) \
            -> Tuple[bool, Any | None]:

        charge_status = None if charge_info is None else charge_info.chrgMgmtData

        if (
                self.abrp_api_key is not None
                and self.abrp_user_token is not None
                and vehicle_status is not None
                and charge_status is not None
        ):
            # Request
            tlm_send_url = f'{self.__base_uri}tlm/send'
            data = {
                # We assume the timestamp is the refresh time or now, we will update it later from GPS if available
                'utc': int(vehicle_status.statusTime) or int(time.time()),
                'soc': (charge_status.bmsPackSOCDsp / 10.0),
                'is_charging': vehicle_status.is_charging,
                'is_parked': vehicle_status.is_parked,
            }

            if vehicle_status.is_parked:
                data.update({
                    # We assume the vehicle is stationary, we will update it later from GPS if available
                    'speed': 0.0,
                })

            # Skip invalid current values reported by the API
            if charge_status.bmsPackCrntV == 0:
                data.update({
                    'power': charge_status.decoded_power,
                    'voltage': charge_status.decoded_voltage,
                    'current': charge_status.decoded_current
                })

            basic_vehicle_status = vehicle_status.basicVehicleStatus
            if basic_vehicle_status is not None:
                data.update(self.__extract_basic_vehicle_status(basic_vehicle_status))

            gps_position = vehicle_status.gpsPosition
            if gps_position is not None:
                data.update(self.__extract_gps_position(gps_position))

            headers = {
                'Authorization': f'APIKEY {self.abrp_api_key}'
            }

            try:
                response = await self.client.post(url=tlm_send_url, headers=headers, params={
                    'token': self.abrp_user_token,
                    'tlm': json.dumps(data)
                })
                await response.aread()
                return True, response.text
            except httpx.ConnectError as ece:
                raise AbrpApiException(f'Connection error: {ece}')
            except httpx.TimeoutException as et:
                raise AbrpApiException(f'Timeout error {et}')
            except httpx.RequestError as e:
                raise AbrpApiException(f'{e}')
            except httpx.HTTPError as ehttp:
                raise AbrpApiException(f'HTTP error {ehttp}')
        else:
            return False, 'ABRP request skipped because of missing configuration'

    @staticmethod
    def __extract_basic_vehicle_status(basic_vehicle_status: BasicVehicleStatus) -> dict:
        data = {}

        exterior_temperature = basic_vehicle_status.exteriorTemperature
        if exterior_temperature is not None and value_in_range(exterior_temperature, -127, 127):
            data['ext_temp'] = exterior_temperature
        mileage = basic_vehicle_status.mileage
        # Skip invalid range readings
        if mileage is not None and value_in_range(mileage, 1, 2147483647):
            data['odometer'] = mileage / 10.0
        range_elec = basic_vehicle_status.fuelRangeElec
        if range_elec is not None and value_in_range(range_elec, 1, 65535):
            data['est_battery_range'] = float(range_elec) / 10.0

        return data

    @staticmethod
    def __extract_gps_position(gps_position: GpsPosition) -> dict:
        data = {}

        # Do not use GPS data if it is not available
        if gps_position.gps_status_decoded not in [GpsStatus.FIX_2D, GpsStatus.FIX_3d]:
            return data

        ts = gps_position.timeStamp
        if value_in_range(ts, 1, 2147483647):
            data['utc'] = ts

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
        if gps_position.gps_status_decoded == GpsStatus.FIX_3d and value_in_range(altitude, -100, 8900):
            data['elevation'] = altitude

        lat_degrees = position.latitude / 1000000.0
        lon_degrees = position.longitude / 1000000.0

        if (
                abs(lat_degrees) <= 90
                and abs(lon_degrees) <= 180
        ):
            data.update({
                'lat': lat_degrees,
                'lon': lon_degrees,
            })

        return data

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
                path=str(request.url).replace(self.__base_uri, "/"),
                body=body,
                headers=dict(request.headers),
            )
        except Exception as e:
            LOG.warning(f"Error invoking request listener: {e}")

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
                path=str(response.url).replace(self.__base_uri, "/"),
                body=body,
                headers=dict(response.headers),
            )
        except Exception as e:
            LOG.warning(f"Error invoking request listener: {e}")
