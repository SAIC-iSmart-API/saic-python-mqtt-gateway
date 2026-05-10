from __future__ import annotations

import argparse
from argparse import Namespace
import json
import logging
from pathlib import Path
import urllib.parse

from configuration import Configuration, TransportProtocol
from configuration.argparse_extensions import (
    ArgumentHelpFormatter,
    EnvDefault,
    cfg_value_to_dict,
    check_bool,
    check_positive,
    check_positive_float,
    check_timezone,
)
from exceptions import MqttGatewayException
from integrations.openwb.charging_station import ChargingStation

LOG = logging.getLogger(__name__)
CHARGING_STATIONS_FILE = "charging-stations.json"


def process_command_line() -> Configuration:
    parser = setup_parser()
    try:
        args = parser.parse_args()
        config = Configuration()

        __setup_mqtt(args, config)

        __setup_saic_api(args, config)

        __setup_gateway_features(args, config)

        __setup_integrations(args, config)

        return config
    except argparse.ArgumentError as err:
        parser.print_help()
        raise SystemExit(err) from err


def __setup_integrations(args: Namespace, config: Configuration) -> None:
    # OpenWB Integration
    __setup_openwb(args, config)
    # Home Assistant Integration
    __setup_home_assistant(args, config)
    # ABRP Integration
    __setup_abrp(args, config)
    # OsmAnd Integration
    __setup_osmand(args, config)


def __setup_gateway_features(args: Namespace, config: Configuration) -> None:
    config.charge_dynamic_polling_min_percentage = (
        args.charge_dynamic_polling_min_percentage
    )
    if args.battery_capacity_mapping:
        cfg_value_to_dict(
            args.battery_capacity_mapping,
            config.battery_capacity_map,
            value_type=check_positive_float,
        )
    try:
        config.messages_request_interval = int(args.messages_request_interval)
    except ValueError as ve:
        msg = f"No valid integer value for messages_request_interval: {args.messages_request_interval}"
        raise SystemExit(msg) from ve
    if args.account_refresh_interval:
        config.account_refresh_interval = args.account_refresh_interval


def __setup_openwb(args: Namespace, config: Configuration) -> None:
    if args.charging_stations_file:
        __process_charging_stations_file(config, args.charging_stations_file)
    else:
        __process_charging_stations_file(config, f"./{CHARGING_STATIONS_FILE}")


def __setup_mqtt(args: Namespace, config: Configuration) -> None:
    config.mqtt_user = args.mqtt_user
    config.mqtt_password = args.mqtt_password
    config.mqtt_client_id = args.mqtt_client_id
    config.mqtt_topic = args.mqtt_topic
    config.mqtt_allow_dots_in_topic = args.mqtt_allow_dots_in_topic
    __parse_mqtt_transport(args, config)


def __parse_mqtt_transport(args: Namespace, config: Configuration) -> None:
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
                config.tls_server_cert_check_hostname = (
                    args.tls_server_cert_check_hostname
                )
        else:
            msg = f"Invalid MQTT URI scheme: {parse_result.scheme}, use tcp or ws"
            raise SystemExit(msg)

        if parse_result.port:
            config.mqtt_port = parse_result.port
        elif config.mqtt_transport_protocol == TransportProtocol.TCP:
            config.mqtt_port = 1883
        else:
            config.mqtt_port = 9001
        config.mqtt_host = str(parse_result.hostname)


def __setup_saic_api(args: Namespace, config: Configuration) -> None:
    config.saic_rest_uri = args.saic_rest_uri
    config.saic_region = args.saic_region
    config.saic_tenant_id = str(args.saic_tenant_id)
    config.saic_user = args.saic_user
    config.saic_password = args.saic_password
    config.saic_phone_country_code = args.saic_phone_country_code
    if args.saic_relogin_delay:
        config.saic_relogin_delay = args.saic_relogin_delay
    if args.saic_read_timeout:
        config.saic_read_timeout = args.saic_read_timeout
    if args.saic_user_timezone is not None:
        config.saic_user_timezone = args.saic_user_timezone


def __setup_home_assistant(args: Namespace, config: Configuration) -> None:
    if args.ha_discovery_enabled is not None:
        config.ha_discovery_enabled = args.ha_discovery_enabled
    if args.publish_raw_api_data is not None:
        config.publish_raw_api_data = args.publish_raw_api_data
    if args.ha_show_unavailable is not None:
        config.ha_show_unavailable = args.ha_show_unavailable
    if args.ha_discovery_prefix:
        config.ha_discovery_prefix = args.ha_discovery_prefix


def __setup_abrp(args: Namespace, config: Configuration) -> None:
    config.abrp_api_key = args.abrp_api_key
    if args.abrp_user_token:
        cfg_value_to_dict(args.abrp_user_token, config.abrp_token_map)
    if args.publish_raw_abrp_data is not None:
        config.publish_raw_abrp_data = args.publish_raw_abrp_data


def __setup_osmand(args: Namespace, config: Configuration) -> None:
    config.osmand_server_uri = args.osmand_server_uri

    if args.osmand_device_id:
        cfg_value_to_dict(args.osmand_device_id, config.osmand_device_id_map)

    if args.publish_raw_osmand_data is not None:
        config.publish_raw_osmand_data = args.publish_raw_osmand_data

    if args.osmand_use_knots is not None:
        config.osmand_use_knots = args.osmand_use_knots


def setup_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="SAIC MQTT Gateway", formatter_class=ArgumentHelpFormatter
    )

    __add_mqtt_argument_group(parser)
    __add_saic_api_argument_group(parser)
    __add_openwb_argument_group(parser)
    __add_homeassistant_argument_group(parser)
    __add_abrp_argument_group(parser)
    add_osmand_argument_group(parser)

    return parser


def __add_mqtt_argument_group(
    parser: argparse.ArgumentParser,
) -> argparse._ArgumentGroup:
    mqtt = parser.add_argument_group("MQTT Broker Configuration")
    mqtt.add_argument(
        "-m",
        "--mqtt-uri",
        help="""The URI to the MQTT Server.
                TCP: tcp://mqtt.eclipseprojects.io:1883
                WebSocket: ws://mqtt.eclipseprojects.io:9001
                TLS: tls://mqtt.eclipseprojects.io:8883""",
        dest="mqtt_uri",
        required=False,
        action=EnvDefault,
        envvar="MQTT_URI",
        type=str,
    )
    mqtt.add_argument(
        "--mqtt-server-cert",
        help="""Path to the server certificate authority file in PEM format for TLS.""",
        dest="tls_server_cert_path",
        required=False,
        action=EnvDefault,
        envvar="MQTT_SERVER_CERT",
        type=str,
    )
    mqtt.add_argument(
        "--mqtt-user",
        help="""The MQTT user name.""",
        dest="mqtt_user",
        required=False,
        action=EnvDefault,
        envvar="MQTT_USER",
        type=str,
    )
    mqtt.add_argument(
        "--mqtt-password",
        help="""The MQTT password.""",
        dest="mqtt_password",
        required=False,
        action=EnvDefault,
        envvar="MQTT_PASSWORD",
        type=str,
    )
    mqtt.add_argument(
        "--mqtt-client-id",
        help="""The MQTT Client Identifier.""",
        default="saic-python-mqtt-gateway",
        dest="mqtt_client_id",
        required=False,
        action=EnvDefault,
        envvar="MQTT_CLIENT_ID",
        type=str,
    )
    mqtt.add_argument(
        "--mqtt-topic-prefix",
        help="""MQTT topic prefix.""",
        default="saic",
        dest="mqtt_topic",
        required=False,
        action=EnvDefault,
        envvar="MQTT_TOPIC",
        type=str,
    )
    mqtt.add_argument(
        "--mqtt-allow-dots-in-topic",
        help="""Allow dots in MQTT topics.""",
        dest="mqtt_allow_dots_in_topic",
        required=False,
        action=EnvDefault,
        default=True,
        type=check_bool,
        envvar="MQTT_ALLOW_DOTS_IN_TOPIC",
    )
    mqtt.add_argument(
        "--mqtt-server-cert-check-hostname",
        help="""Check TLS certificate hostname when using custom certificate.
                Set to (False) when using self-signed certificate without a matching hostname.
                This option might be insecure.""",
        dest="tls_server_cert_check_hostname",
        required=False,
        action=EnvDefault,
        envvar="MQTT_SERVER_CERT_CHECK_HOSTNAME",
        default=True,
        type=check_bool,
    )
    return mqtt


def __add_saic_api_argument_group(
    parser: argparse.ArgumentParser,
) -> argparse._ArgumentGroup:
    saic_api = parser.add_argument_group(
        "SAIC API Configuration",
        "Configuration for the SAIC API connection.",
    )
    saic_api.add_argument(
        "-s",
        "--saic-rest-uri",
        help="""The SAIC uri. Default is European Production Endpoint""",
        default="https://gateway-mg-eu.soimt.com/api.app/v1/",
        dest="saic_rest_uri",
        required=False,
        action=EnvDefault,
        type=str,
        envvar="SAIC_REST_URI",
    )
    saic_api.add_argument(
        "-u",
        "--saic-user",
        help="""The SAIC user name.""",
        dest="saic_user",
        required=True,
        action=EnvDefault,
        envvar="SAIC_USER",
        type=str,
    )
    saic_api.add_argument(
        "-p",
        "--saic-password",
        help="""The SAIC password.""",
        dest="saic_password",
        required=True,
        action=EnvDefault,
        envvar="SAIC_PASSWORD",
        type=str,
    )
    saic_api.add_argument(
        "--saic-phone-country-code",
        help="""The SAIC phone country code.""",
        dest="saic_phone_country_code",
        required=False,
        action=EnvDefault,
        envvar="SAIC_PHONE_COUNTRY_CODE",
        type=str,
    )
    saic_api.add_argument(
        "--saic-region",
        help="""The SAIC API region.""",
        default="eu",
        dest="saic_region",
        required=False,
        action=EnvDefault,
        envvar="SAIC_REGION",
        type=str,
    )
    saic_api.add_argument(
        "--saic-tenant-id",
        help="""The SAIC API tenant id.""",
        default="459771",
        dest="saic_tenant_id",
        required=False,
        action=EnvDefault,
        envvar="SAIC_TENANT_ID",
        type=str,
    )
    saic_api.add_argument(
        "--battery-capacity-mapping",
        help="""The mapping of VIN to full battery capacity.
                Multiple mappings can be provided separated by comma.
                Example: LSJXXXX=54.0,LSJYYYY=64.0,""",
        dest="battery_capacity_mapping",
        required=False,
        action=EnvDefault,
        envvar="BATTERY_CAPACITY_MAPPING",
        type=str,
    )
    saic_api.add_argument(
        "--saic-relogin-delay",
        help="""How long to wait before attempting another login to the SAIC API.""",
        dest="saic_relogin_delay",
        required=False,
        action=EnvDefault,
        envvar="SAIC_RELOGIN_DELAY",
        type=check_positive,
    )
    saic_api.add_argument(
        "--saic-read-timeout",
        help="""HTTP Read timeout for the SAIC API.""",
        dest="saic_read_timeout",
        required=False,
        action=EnvDefault,
        envvar="SAIC_READ_TIMEOUT",
        type=check_positive_float,
    )
    saic_api.add_argument(
        "--saic-user-timezone",
        help="""Force the account timezone instead of trusting the SAIC API value.
                Accepts an IANA timezone name (e.g. Australia/Sydney) or the
                GMT+HH:MM format. Any discrepancy between this value and the
                timezone reported by the API is logged.""",
        dest="saic_user_timezone",
        required=False,
        action=EnvDefault,
        envvar="SAIC_USER_TIMEZONE",
        type=check_timezone,
    )
    saic_api.add_argument(
        "--messages-request-interval",
        help="""The interval for retrieving messages in seconds.""",
        dest="messages_request_interval",
        required=False,
        action=EnvDefault,
        envvar="MESSAGES_REQUEST_INTERVAL",
        default=60,
        type=check_positive,
    )
    saic_api.add_argument(
        "--account-refresh-interval",
        help="""The interval for refreshing account-level data (vehicle list, timezone) in seconds.""",
        dest="account_refresh_interval",
        required=False,
        action=EnvDefault,
        envvar="ACCOUNT_REFRESH_INTERVAL",
        default=24 * 60 * 60,
        type=check_positive,
    )
    saic_api.add_argument(
        "--charge-min-percentage",
        help="""How many percentage points we should try to refresh the charge state.""",
        dest="charge_dynamic_polling_min_percentage",
        required=False,
        action=EnvDefault,
        envvar="CHARGE_MIN_PERCENTAGE",
        default="1.0",
        type=check_positive_float,
    )
    saic_api.add_argument(
        "--publish-raw-api-data",
        help="""Publish raw SAIC API request/response to MQTT.""",
        dest="publish_raw_api_data",
        required=False,
        action=EnvDefault,
        envvar="PUBLISH_RAW_API_DATA_ENABLED",
        default=False,
        type=check_bool,
    )
    return saic_api


def __add_openwb_argument_group(
    parser: argparse.ArgumentParser,
) -> argparse._ArgumentGroup:
    openwb_integration = parser.add_argument_group(
        "OpenWB Integration", "Configuration for the OpenWB integration."
    )
    openwb_integration.add_argument(
        "--charging-stations-json",
        help="""Custom charging stations configuration file name""",
        dest="charging_stations_file",
        required=False,
        action=EnvDefault,
        envvar="CHARGING_STATIONS_JSON",
        type=str,
    )
    return openwb_integration


def __add_homeassistant_argument_group(
    parser: argparse.ArgumentParser,
) -> argparse._ArgumentGroup:
    homeassistant_integration = parser.add_argument_group(
        "Home Assistant Integration",
        "Configuration for the Home Assistant integration.",
    )
    homeassistant_integration.add_argument(
        "--ha-discovery",
        help="""Enable Home Assistant Discovery.""",
        dest="ha_discovery_enabled",
        required=False,
        action=EnvDefault,
        envvar="HA_DISCOVERY_ENABLED",
        default=True,
        type=check_bool,
    )
    homeassistant_integration.add_argument(
        "--ha-discovery-prefix",
        help="""Home Assistant Discovery Prefix.""",
        dest="ha_discovery_prefix",
        required=False,
        action=EnvDefault,
        envvar="HA_DISCOVERY_PREFIX",
        default="homeassistant",
    )
    homeassistant_integration.add_argument(
        "--ha-show-unavailable",
        help="""Show entities as Unavailable in Home Assistant when car polling fails.""",
        dest="ha_show_unavailable",
        required=False,
        action=EnvDefault,
        envvar="HA_SHOW_UNAVAILABLE",
        default=True,
        type=check_bool,
    )
    return homeassistant_integration


def __add_abrp_argument_group(
    parser: argparse.ArgumentParser,
) -> argparse._ArgumentGroup:
    abrp_integration = parser.add_argument_group(
        "A Better Route Planner (ABRP) Integration",
        "Configuration for the A Better Route Planner integration.",
    )
    abrp_integration.add_argument(
        "--abrp-api-key",
        help="""The API key for the A Better Route Planer telemetry API.""",
        default="8cfc314b-03cd-4efe-ab7d-4431cd8f2e2d",
        dest="abrp_api_key",
        required=False,
        action=EnvDefault,
        envvar="ABRP_API_KEY",
        type=str,
    )
    abrp_integration.add_argument(
        "--abrp-user-token",
        help="""The mapping of VIN to ABRP User Token.
                Multiple mappings can be provided seperated by ,
                Example: LSJXXXX=12345-abcdef,LSJYYYY=67890-ghijkl,""",
        dest="abrp_user_token",
        required=False,
        action=EnvDefault,
        envvar="ABRP_USER_TOKEN",
        type=str,
    )
    abrp_integration.add_argument(
        "--publish-raw-abrp-data",
        help="""Publish raw ABRP API request/response to MQTT.""",
        dest="publish_raw_abrp_data",
        required=False,
        action=EnvDefault,
        envvar="PUBLISH_RAW_ABRP_DATA_ENABLED",
        default=False,
        type=check_bool,
    )
    return abrp_integration


def add_osmand_argument_group(
    parser: argparse.ArgumentParser,
) -> argparse._ArgumentGroup:
    osmand_integration = parser.add_argument_group(
        "OsmAnd Integration",
        "Configuration for the OsmAnd integration.",
    )
    osmand_integration.add_argument(
        "--osmand-server-uri",
        help="""The URL of your OsmAnd Server.""",
        default=None,
        dest="osmand_server_uri",
        required=False,
        action=EnvDefault,
        envvar="OSMAND_SERVER_URI",
        type=str,
    )
    osmand_integration.add_argument(
        "--osmand-device-id",
        help="""The mapping of VIN to OsmAnd Device ID.
                Multiple mappings can be provided seperated by ,
                Example: LSJXXXX=12345-abcdef,LSJYYYY=67890-ghijkl,
                Uses the car VIN as Device ID if not set""",
        dest="osmand_device_id",
        required=False,
        action=EnvDefault,
        envvar="OSMAND_DEVICE_ID",
        type=str,
    )
    osmand_integration.add_argument(
        "--osmand-use-knots",
        help="""Whether to use knots of kph as a speed unit in OsmAnd messages to ensure compatibilty with Traccar.""",
        dest="osmand_use_knots",
        required=False,
        action=EnvDefault,
        envvar="OSMAND_USE_KNOTS",
        default=True,
        type=check_bool,
    )
    osmand_integration.add_argument(
        "--publish-raw-osmand-data",
        help="""Publish raw ABRP OsmAnd request/response to MQTT.""",
        dest="publish_raw_osmand_data",
        required=False,
        action=EnvDefault,
        envvar="PUBLISH_RAW_OSMAND_DATA_ENABLED",
        default=False,
        type=check_bool,
    )
    return osmand_integration


def __process_charging_stations_file(config: Configuration, json_file: str) -> None:
    try:
        with Path(json_file).open(encoding="utf-8") as f:
            data = json.load(f)

            for item in data:
                vin = item["vin"]
                charging_station = ChargingStation(
                    vin=vin,
                    charge_state_topic=item["chargeStateTopic"],
                    charging_value=item["chargingValue"],
                    soc_topic=item.get("socTopic"),
                    soc_ts_topic=item.get("socTsTopic"),
                    range_topic=item.get("rangeTopic"),
                    connected_topic=item.get("chargerConnectedTopic"),
                    connected_value=item.get("chargerConnectedValue"),
                    imported_energy_topic=item.get("importedEnergyTopic"),
                )
                config.charging_stations_by_vin[vin] = charging_station
    except FileNotFoundError:
        LOG.warning(f"File {json_file} does not exist")
    except json.JSONDecodeError as e:
        msg = f"Reading {json_file} failed"
        raise MqttGatewayException(msg) from e
