from charging_station import ChargingStation


class Configuration:
    def __init__(self):
        self.saic_user = ''
        self.saic_password = ''
        self.saic_uri = ''
        self.saic_rest_uri = 'https://gateway-eu.soimt.com/'
        self.saic_relogin_delay = 15 * 60  # in seconds
        self.abrp_token_map: dict[str, str] = {}
        self.abrp_api_key = ''
        self.mqtt_host = ''
        self.mqtt_port = -1
        self.mqtt_transport_protocol = ''
        self.mqtt_user = ''
        self.mqtt_password = ''
        self.mqtt_topic = ''
        self.charging_stations_by_vin: dict[str, ChargingStation] = {}
        self.anonymized_publishing = False
        self.messages_request_interval = 60  # in seconds
        self.ha_discovery_enabled = True
        self.ha_discovery_prefix = 'homeassistant'
        self.charge_dynamic_polling_min_percentage: float = 1.0
