from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import urllib.parse

from configuration import Configuration, TransportProtocol
from configuration.argparse_extensions import (
    EnvDefault,
    cfg_value_to_dict,
    check_bool,
    check_positive,
    check_positive_float,
)
from exceptions import MqttGatewayException
from integrations.openwb.charging_station import ChargingStation

LOG = logging.getLogger(__name__)
CHARGING_STATIONS_FILE = "charging-stations.json"


def __process_charging_stations_file(config: Configuration, json_file: str) -> None:
    try:
        with Path(json_file).open(encoding="utf-8") as f:
            data = json.load(f)

            for item in data:
                charge_state_topic = item["chargeStateTopic"]
                charging_value = item["chargingValue"]
                vin = item["vin"]
                if "socTopic" in item:
                    charging_station = ChargingStation(
                        vin, charge_state_topic, charging_value, item["socTopic"]
                    )
                else:
                    charging_station = ChargingStation(
                        vin, charge_state_topic, charging_value
                    )
                if "rangeTopic" in item:
                    charging_station.range_topic = item["rangeTopic"]
                if "chargerConnectedTopic" in item:
                    charging_station.connected_topic = item["chargerConnectedTopic"]
                if "chargerConnectedValue" in item:
                    charging_station.connected_value = item["chargerConnectedValue"]
                config.charging_stations_by_vin[vin] = charging_station
    except FileNotFoundError:
        LOG.warning(f"File {json_file} does not exist")
    except json.JSONDecodeError as e:
        msg = f"Reading {json_file} failed"
        raise MqttGatewayException(msg) from e


def process_arguments() -> Configuration:
    config = Configuration()
    parser = argparse.ArgumentParser(prog="MQTT Gateway")
    try:
        parser.add_argument(
            "-m",
            "--mqtt-uri",
            help="The URI to the MQTT Server. Environment Variable: MQTT_URI,"
            "TCP: tcp://mqtt.eclipseprojects.io:1883 "
            "WebSocket: ws://mqtt.eclipseprojects.io:9001"
            "TLS: tls://mqtt.eclipseprojects.io:8883",
            dest="mqtt_uri",
            required=False,
            action=EnvDefault,
            envvar="MQTT_URI",
        )
        parser.add_argument(
            "--mqtt-server-cert",
            help="Path to the server certificate authority file in PEM format for TLS.",
            dest="tls_server_cert_path",
            required=False,
            action=EnvDefault,
            envvar="MQTT_SERVER_CERT",
        )
        parser.add_argument(
            "--mqtt-user",
            help="The MQTT user name. Environment Variable: MQTT_USER",
            dest="mqtt_user",
            required=False,
            action=EnvDefault,
            envvar="MQTT_USER",
        )
        parser.add_argument(
            "--mqtt-password",
            help="The MQTT password. Environment Variable: MQTT_PASSWORD",
            dest="mqtt_password",
            required=False,
            action=EnvDefault,
            envvar="MQTT_PASSWORD",
        )
        parser.add_argument(
            "--mqtt-client-id",
            help="The MQTT Client Identifier. Environment Variable: "
            "MQTT_CLIENT_ID "
            "Default is saic-python-mqtt-gateway",
            default="saic-python-mqtt-gateway",
            dest="mqtt_client_id",
            required=False,
            action=EnvDefault,
            envvar="MQTT_CLIENT_ID",
        )
        parser.add_argument(
            "--mqtt-topic-prefix",
            help="MQTT topic prefix. Environment Variable: MQTT_TOPIC Default is saic",
            default="saic",
            dest="mqtt_topic",
            required=False,
            action=EnvDefault,
            envvar="MQTT_TOPIC",
        )
        parser.add_argument(
            "--mqtt-allow-dots-in-topic",
            help="Allow dots in MQTT topics. Environment Variable: MQTT_ALLOW_DOTS_IN_TOPIC Default is True",
            dest="mqtt_allow_dots_in_topic",
            required=False,
            action=EnvDefault,
            default=True,
            type=check_bool,
            envvar="MQTT_ALLOW_DOTS_IN_TOPIC",
        )
        parser.add_argument(
            "-s",
            "--saic-rest-uri",
            help="The SAIC uri. Environment Variable: SAIC_REST_URI Default is the European "
            "Production Endpoint: https://tap-eu.soimt.com",
            default="https://gateway-mg-eu.soimt.com/api.app/v1/",
            dest="saic_rest_uri",
            required=False,
            action=EnvDefault,
            envvar="SAIC_REST_URI",
        )
        parser.add_argument(
            "-u",
            "--saic-user",
            help="The SAIC user name. Environment Variable: SAIC_USER",
            dest="saic_user",
            required=True,
            action=EnvDefault,
            envvar="SAIC_USER",
        )
        parser.add_argument(
            "-p",
            "--saic-password",
            help="The SAIC password. Environment Variable: SAIC_PASSWORD",
            dest="saic_password",
            required=True,
            action=EnvDefault,
            envvar="SAIC_PASSWORD",
        )
        parser.add_argument(
            "--saic-phone-country-code",
            help="The SAIC phone country code. Environment Variable: SAIC_PHONE_COUNTRY_CODE",
            dest="saic_phone_country_code",
            required=False,
            action=EnvDefault,
            envvar="SAIC_PHONE_COUNTRY_CODE",
        )
        parser.add_argument(
            "--saic-region",
            "--saic-region",
            help="The SAIC API region. Environment Variable: SAIC_REGION",
            default="eu",
            dest="saic_region",
            required=False,
            action=EnvDefault,
            envvar="SAIC_REGION",
        )
        parser.add_argument(
            "--saic-tenant-id",
            help="The SAIC API tenant id. Environment Variable: SAIC_TENANT_ID",
            default="459771",
            dest="saic_tenant_id",
            required=False,
            action=EnvDefault,
            envvar="SAIC_TENANT_ID",
        )
        parser.add_argument(
            "--battery-capacity-mapping",
            help="The mapping of VIN to full batteryc"
            " apacity. Multiple mappings can be provided separated"
            " by , Example: LSJXXXX=54.0,LSJYYYY=64.0,"
            " Environment Variable: BATTERY_CAPACITY_MAPPING",
            dest="battery_capacity_mapping",
            required=False,
            action=EnvDefault,
            envvar="BATTERY_CAPACITY_MAPPING",
        )
        parser.add_argument(
            "--charging-stations-json",
            help="Custom charging stations configuration file name",
            dest="charging_stations_file",
            required=False,
            action=EnvDefault,
            envvar="CHARGING_STATIONS_JSON",
        )
        parser.add_argument(
            "--saic-relogin-delay",
            help="How long to wait before attempting another login to the SAIC API. Environment "
            "Variable: SAIC_RELOGIN_DELAY",
            dest="saic_relogin_delay",
            required=False,
            action=EnvDefault,
            envvar="SAIC_RELOGIN_DELAY",
            type=check_positive,
        )
        parser.add_argument(
            "--saic-read-timeout",
            help="HTTP Read timeout for the SAIC API. Environment "
            "Variable: SAIC_READ_TIMEOUT",
            dest="saic_read_timeout",
            required=False,
            action=EnvDefault,
            envvar="SAIC_READ_TIMEOUT",
            type=check_positive_float,
        )
        parser.add_argument(
            "--ha-discovery",
            help="Enable Home Assistant Discovery. Environment Variable: HA_DISCOVERY_ENABLED",
            dest="ha_discovery_enabled",
            required=False,
            action=EnvDefault,
            envvar="HA_DISCOVERY_ENABLED",
            default=True,
            type=check_bool,
        )
        parser.add_argument(
            "--ha-discovery-prefix",
            help="Home Assistant Discovery Prefix. Environment Variable: HA_DISCOVERY_PREFIX",
            dest="ha_discovery_prefix",
            required=False,
            action=EnvDefault,
            envvar="HA_DISCOVERY_PREFIX",
            default="homeassistant",
        )
        parser.add_argument(
            "--ha-show-unavailable",
            help="Show entities as Unavailable in Home Assistant when car polling fails. "
            "Environment Variable: HA_SHOW_UNAVAILABLE",
            dest="ha_show_unavailable",
            required=False,
            action=EnvDefault,
            envvar="HA_SHOW_UNAVAILABLE",
            default=True,
            type=check_bool,
        )
        parser.add_argument(
            "--messages-request-interval",
            help="The interval for retrieving messages in seconds. Environment Variable: "
            "MESSAGES_REQUEST_INTERVAL",
            dest="messages_request_interval",
            required=False,
            action=EnvDefault,
            envvar="MESSAGES_REQUEST_INTERVAL",
            default=60,
        )
        parser.add_argument(
            "--charge-min-percentage",
            help="How many % points we should try to refresh the charge state. Environment Variable: "
            "CHARGE_MIN_PERCENTAGE",
            dest="charge_dynamic_polling_min_percentage",
            required=False,
            action=EnvDefault,
            envvar="CHARGE_MIN_PERCENTAGE",
            default="1.0",
            type=check_positive_float,
        )
        parser.add_argument(
            "--publish-raw-api-data",
            help="Publish raw SAIC API request/response to MQTT. Environment Variable: "
            "PUBLISH_RAW_API_DATA_ENABLED",
            dest="publish_raw_api_data",
            required=False,
            action=EnvDefault,
            envvar="PUBLISH_RAW_API_DATA_ENABLED",
            default=False,
            type=check_bool,
        )

        # ABRP Integration
        parser.add_argument(
            "--abrp-api-key",
            help="The API key for the A Better Route Planer telemetry API."
            " Default is the open source telemetry"
            " API key 8cfc314b-03cd-4efe-ab7d-4431cd8f2e2d."
            " Environment Variable: ABRP_API_KEY",
            default="8cfc314b-03cd-4efe-ab7d-4431cd8f2e2d",
            dest="abrp_api_key",
            required=False,
            action=EnvDefault,
            envvar="ABRP_API_KEY",
        )
        parser.add_argument(
            "--abrp-user-token",
            help="The mapping of VIN to ABRP User Token."
            " Multiple mappings can be provided seperated by ,"
            " Example: LSJXXXX=12345-abcdef,LSJYYYY=67890-ghijkl,"
            " Environment Variable: ABRP_USER_TOKEN",
            dest="abrp_user_token",
            required=False,
            action=EnvDefault,
            envvar="ABRP_USER_TOKEN",
        )
        parser.add_argument(
            "--publish-raw-abrp-data",
            help="Publish raw ABRP API request/response to MQTT. Environment Variable: "
            "PUBLISH_RAW_ABRP_DATA_ENABLED",
            dest="publish_raw_abrp_data",
            required=False,
            action=EnvDefault,
            envvar="PUBLISH_RAW_ABRP_DATA_ENABLED",
            default=False,
            type=check_bool,
        )
        # OsmAnd Integration
        parser.add_argument(
            "--osmand-server-uri",
            help="The URL of your OsmAnd Server."
            " Default unset"
            " Environment Variable: OSMAND_SERVER_URI",
            default=None,
            dest="osmand_server_uri",
            required=False,
            action=EnvDefault,
            envvar="OSMAND_SERVER_URI",
        )
        parser.add_argument(
            "--osmand-device-id",
            help="The mapping of VIN to OsmAnd Device ID."
            " Multiple mappings can be provided seperated by ,"
            " Example: LSJXXXX=12345-abcdef,LSJYYYY=67890-ghijkl,"
            " Default is to use the car VIN as Device ID, "
            " Environment Variable: OSMAND_DEVICE_ID",
            dest="osmand_device_id",
            required=False,
            action=EnvDefault,
            envvar="OSMAND_DEVICE_ID",
        )
        parser.add_argument(
            "--publish-raw-osmand-data",
            help="Publish raw ABRP OsmAnd request/response to MQTT. Environment Variable: "
            "PUBLISH_RAW_OSMAND_DATA_ENABLED",
            dest="publish_raw_osmand_data",
            required=False,
            action=EnvDefault,
            envvar="PUBLISH_RAW_OSMAND_DATA_ENABLED",
            default=False,
            type=check_bool,
        )

        args = parser.parse_args()
        config.mqtt_user = args.mqtt_user
        config.mqtt_password = args.mqtt_password
        config.mqtt_client_id = args.mqtt_client_id
        config.charge_dynamic_polling_min_percentage = (
            args.charge_dynamic_polling_min_percentage
        )

        if args.saic_relogin_delay:
            config.saic_relogin_delay = args.saic_relogin_delay

        if args.saic_read_timeout:
            config.saic_read_timeout = args.saic_read_timeout

        config.mqtt_topic = args.mqtt_topic
        config.mqtt_allow_dots_in_topic = args.mqtt_allow_dots_in_topic
        config.saic_rest_uri = args.saic_rest_uri
        config.saic_region = args.saic_region
        config.saic_tenant_id = str(args.saic_tenant_id)
        config.saic_user = args.saic_user
        config.saic_password = args.saic_password
        config.saic_phone_country_code = args.saic_phone_country_code
        if args.battery_capacity_mapping:
            cfg_value_to_dict(
                args.battery_capacity_mapping,
                config.battery_capacity_map,
                value_type=check_positive_float,
            )
        if args.charging_stations_file:
            __process_charging_stations_file(config, args.charging_stations_file)
        else:
            __process_charging_stations_file(config, f"./{CHARGING_STATIONS_FILE}")

        config.saic_password = args.saic_password

        if args.ha_discovery_enabled is not None:
            config.ha_discovery_enabled = args.ha_discovery_enabled

        if args.publish_raw_api_data is not None:
            config.publish_raw_api_data = args.publish_raw_api_data

        if args.ha_show_unavailable is not None:
            config.ha_show_unavailable = args.ha_show_unavailable

        if args.ha_discovery_prefix:
            config.ha_discovery_prefix = args.ha_discovery_prefix

        try:
            config.messages_request_interval = int(args.messages_request_interval)
        except ValueError as ve:
            msg = f"No valid integer value for messages_request_interval: {args.messages_request_interval}"
            raise SystemExit(msg) from ve

        if args.mqtt_uri is not None and len(args.mqtt_uri) > 0:
            parse_result = urllib.parse.urlparse(args.mqtt_uri)
            if parse_result.scheme == "tcp":
                config.mqtt_transport_protocol = TransportProtocol.TCP
            elif parse_result.scheme == "ws":
                config.mqtt_transport_protocol = TransportProtocol.WS
            elif parse_result.scheme == "tls":
                config.mqtt_transport_protocol = TransportProtocol.TLS
                if args.tls_server_cert_path:
                    config.tls_server_cert_path = args.tls_server_cert_path
                else:
                    msg = f"No server certificate authority file provided for TLS MQTT URI {args.mqtt_uri}"
                    raise SystemExit(msg)
            else:
                msg = f"Invalid MQTT URI scheme: {parse_result.scheme}, use tcp or ws"
                raise SystemExit(msg)

            if not parse_result.port:
                if config.mqtt_transport_protocol == TransportProtocol.TCP:
                    config.mqtt_port = 1883
                else:
                    config.mqtt_port = 9001
            else:
                config.mqtt_port = parse_result.port

            config.mqtt_host = str(parse_result.hostname)

        # ABRP Integration
        config.abrp_api_key = args.abrp_api_key
        if args.abrp_user_token:
            cfg_value_to_dict(args.abrp_user_token, config.abrp_token_map)
        if args.publish_raw_abrp_data is not None:
            config.publish_raw_abrp_data = args.publish_raw_abrp_data

        # OsmAnd Integration
        config.osmand_server_uri = args.osmand_server_uri
        if args.osmand_device_id:
            cfg_value_to_dict(args.osmand_device_id, config.osmand_device_id_map)
        if args.publish_raw_osmand_data is not None:
            config.publish_raw_osmand_data = args.publish_raw_osmand_data

        return config
    except argparse.ArgumentError as err:
        parser.print_help()
        raise SystemExit(err) from err
