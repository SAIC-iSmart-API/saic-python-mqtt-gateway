from enum import Enum

from integrations.openwb.charging_station import ChargingStation


class TransportProtocol(Enum):
    def __init__(self, transport_mechanism: str, with_tls: bool):
        self.transport_mechanism = transport_mechanism
        self.with_tls = with_tls

    TCP = 'tcp', False
    WS = 'websockets', False
    TLS = 'tcp', True


class Configuration:
    def __init__(self):
        self.saic_user: str | None = None
        self.saic_password: str | None = None
        self.saic_phone_country_code: str | None = None
        self.saic_rest_uri: str = 'https://gateway-mg-eu.soimt.com/api.app/v1/'
        self.saic_region: str = 'eu'
        self.saic_tenant_id: str = '459771'
        self.saic_relogin_delay: int = 15 * 60  # in seconds
        self.abrp_token_map: dict[str, str] = {}
        self.battery_capacity_map: dict[str, float] = {}
        self.abrp_api_key: str | None = None
        self.mqtt_host: str | None = None
        self.mqtt_port: int | None = None
        self.mqtt_transport_protocol: TransportProtocol | None = None
        self.tls_server_cert_path: str | None = None
        self.mqtt_user: str | None = None
        self.mqtt_password: str | None = None
        self.mqtt_client_id: str = 'saic-python-mqtt-gateway'
        self.mqtt_topic: str | None = None
        self.charging_stations_by_vin: dict[str, ChargingStation] = {}
        self.anonymized_publishing: bool = False
        self.messages_request_interval: int = 60  # in seconds
        self.ha_discovery_enabled: bool = True
        self.ha_discovery_prefix: str = 'homeassistant'
        self.ha_show_unavailable: bool = True
        self.charge_dynamic_polling_min_percentage: float = 1.0
        self.publish_raw_api_data: bool = False
        self.publish_raw_abrp_data: bool = False
