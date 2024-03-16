import json
import time
from typing import Any, Tuple

import httpx
from saic_ismart_client_ng.api.schema import GpsPosition
from saic_ismart_client_ng.api.vehicle import VehicleStatusResp
from saic_ismart_client_ng.api.vehicle.schema import BasicVehicleStatus
from saic_ismart_client_ng.api.vehicle_charging import ChargeInfoResp


class AbrpApiException(Exception):
    def __init__(self, msg: str):
        self.message = msg

    def __str__(self):
        return self.message


class AbrpApi:
    def __init__(self, abrp_api_key: str, abrp_user_token: str) -> None:
        self.abrp_api_key = abrp_api_key
        self.abrp_user_token = abrp_user_token
        self.client = httpx.AsyncClient()

    async def update_abrp(self, vehicle_status: VehicleStatusResp, charge_info: ChargeInfoResp) \
            -> Tuple[bool, Any | None]:

        charge_status = None if charge_info is None else charge_info.chrgMgmtData

        if (
                self.abrp_api_key is not None
                and self.abrp_user_token is not None
                and vehicle_status is not None
                and charge_status is not None
        ):
            # Request
            tlm_send_url = 'https://api.iternio.com/1/tlm/send'
            data = {
                # We assume the timestamp is now, we will update it later from GPS if available
                'utc': int(time.time()),
                'soc': (charge_status.bmsPackSOCDsp / 10.0),
                'power': charge_status.decoded_power,
                'voltage': charge_status.decoded_voltage,
                'current': charge_status.decoded_current,
                'is_charging': vehicle_status.is_charging,
                'is_parked': vehicle_status.is_parked,
            }

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
        if exterior_temperature is not None and exterior_temperature != -128:
            data['ext_temp'] = exterior_temperature
        mileage = basic_vehicle_status.mileage
        if mileage is not None and mileage > 0:
            data['odometer'] = mileage / 10.0
        range_elec = basic_vehicle_status.fuelRangeElec
        if range_elec is not None and range_elec > 0:
            data['est_battery_range'] = float(range_elec) / 10.0

        return data

    @staticmethod
    def __extract_gps_position(gps_position: GpsPosition) -> dict:

        # Do not transmit GPS data if we have no timestamp
        if gps_position.timeStamp is None or gps_position.timeStamp <= 0:
            return {}

        way_point = gps_position.wayPoint

        # Do not transmit GPS data if we have no speed info
        if way_point is None:
            return {}

        data = {
            'utc': gps_position.timeStamp,  # FIXME: check this is actually UTC seconds
            'speed': (way_point.speed / 10.0),
            'heading': way_point.heading,
        }

        position = way_point.position

        if position is None:
            return data

        lat_degrees = position.latitude / 1000000.0
        lon_degrees = position.longitude / 1000000.0

        if (
                abs(lat_degrees) <= 90
                and abs(lon_degrees) <= 180
        ):
            data.update({
                'lat': lat_degrees,
                'lon': lon_degrees,
                'elevation': position.altitude,
            })

        return data
