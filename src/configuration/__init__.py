from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from integrations.openwb.charging_station import ChargingStation


class TransportProtocol(Enum):
    def __init__(self, transport_mechanism: str, with_tls: bool) -> None:
        self.transport_mechanism = transport_mechanism
        self.with_tls = with_tls

    TCP = "tcp", False
    WS = "websockets", False
    TLS = "tcp", True


class Configuration:
    def __init__(self) -> None:
        self.saic_user: str | None = None
        self.saic_password: str | None = None
        self.__saic_phone_country_code: str | None = None
        self.saic_rest_uri: str = "https://gateway-mg-eu.soimt.com/api.app/v1/"
        self.saic_region: str = "eu"
        self.saic_tenant_id: str = "459771"
        self.saic_relogin_delay: int = 15 * 60  # in seconds
        self.saic_read_timeout: float = 10.0  # in seconds
        self.battery_capacity_map: dict[str, float] = {}
        self.mqtt_host: str | None = None
        self.mqtt_port: int = 1883
        self.mqtt_transport_protocol: TransportProtocol = TransportProtocol.TCP
        self.tls_server_cert_path: str | None = None
        self.mqtt_user: str | None = None
        self.mqtt_password: str | None = None
        self.mqtt_client_id: str = "saic-python-mqtt-gateway"
        self.mqtt_topic: str = "saic"
        self.mqtt_allow_dots_in_topic: bool = True
        self.charging_stations_by_vin: dict[str, ChargingStation] = {}
        self.anonymized_publishing: bool = False
        self.messages_request_interval: int = 60  # in seconds
        self.ha_discovery_enabled: bool = True
        self.ha_discovery_prefix: str = "homeassistant"
        self.ha_show_unavailable: bool = True
        self.charge_dynamic_polling_min_percentage: float = 1.0
        self.publish_raw_api_data: bool = False

        # ABRP Integration
        self.abrp_token_map: dict[str, str] = {}
        self.abrp_api_key: str | None = None
        self.publish_raw_abrp_data: bool = False

        # OsmAnd Integration
        self.osmand_device_id_map: dict[str, str] = {}
        self.osmand_server_uri: str | None = None
        self.publish_raw_osmand_data: bool = False

    @property
    def is_mqtt_enabled(self) -> bool:
        return self.mqtt_host is not None and len(str(self.mqtt_host)) > 0

    @property
    def username_is_email(self) -> bool:
        return self.saic_user is not None and "@" in self.saic_user

    @property
    def ha_lwt_topic(self) -> str:
        return f"{self.ha_discovery_prefix}/status"

    @property
    def saic_phone_country_code(self) -> str | None:
        return None if self.username_is_email else self.__saic_phone_country_code

    @saic_phone_country_code.setter
    def saic_phone_country_code(self, country_code: str | None) -> None:
        self.__saic_phone_country_code = country_code
