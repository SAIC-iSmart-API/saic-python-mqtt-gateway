import json
import time

import requests

from vehicle import VehicleState


class AbrpApiException(Exception):
    def __init__(self, msg: str):
        self.message = msg

    def __str__(self):
        return self.message


class AbrpApi:
    def __init__(self, abrp_api_key: str, abrp_user_token: str) -> None:
        self.abrp_api_key = abrp_api_key
        self.abrp_user_token = abrp_user_token

    def update_abrp(self, vehicle_state: VehicleState) -> str:
        if (
                self.abrp_api_key is not None
                and self.abrp_user_token is not None
                and vehicle_state is not None
        ):
            # Request
            tlm_send_url = 'https://api.iternio.com/1/tlm/send'
            data = {
                'utc': int(time.time()),  # Assuming the timestamp is now, we will update it later from GPS if available
                'soc': vehicle_state.soc,
                'power': vehicle_state.power,
                'voltage': vehicle_state.voltage,
                'current': vehicle_state.current,
                'is_charging': vehicle_state.is_charging,
                'is_parked': vehicle_state.is_parked
            }

            if vehicle_state.exterior_temperature > 0:
                data['ext_temp'] = vehicle_state.exterior_temperature
            if vehicle_state.mileage > 0:
                data['odometer'] = vehicle_state.mileage
            if vehicle_state.electric_range > 0:
                data['est_battery_range'] = vehicle_state.electric_range

            if(
                'utc' in vehicle_state.gps_data
                and 'speed' in vehicle_state.gps_data
            ):
                data.update(vehicle_state.gps_data)

            headers = {
                'Authorization': f'APIKEY {self.abrp_api_key}'
            }

            try:
                response = requests.post(url=tlm_send_url, headers=headers, params={
                    'token': self.abrp_user_token,
                    'tlm': json.dumps(data)
                })
                return response.content.decode()
            except requests.exceptions.ConnectionError as ece:
                raise AbrpApiException(f'Connection error: {ece}')
            except requests.exceptions.Timeout as et:
                raise AbrpApiException(f'Timeout error {et}')
            except requests.exceptions.HTTPError as ehttp:
                raise AbrpApiException(f'HTTP error {ehttp}')
            except requests.exceptions.RequestException as e:
                raise AbrpApiException(f'{e}')
        else:
            return 'ABRP request skipped because of missing configuration'
