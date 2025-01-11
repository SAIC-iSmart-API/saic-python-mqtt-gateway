# SAIC MQTT Gateway

A service that queries the data from an MG iSMART account and publishes the data over MQTT.

MG iSMART is the connectivity system in your MG car (MG5, MG4, ZS...).

The implementation is based on the findings from
the [SAIC-iSmart-API Documentation](https://github.com/SAIC-iSmart-API/documentation) project.

## Prerequisites

* You have an iSMART account (can be created in the iSMART app)
* Your car needs to be registered to your account

## Configuration

Configuration parameters can be provided as command line parameters or environment variables (this is what you typically
do when you run the service from a docker container).

### SAIC API

| CMD param                   | ENV variable                 | Description                                                                                                                                                                         |
|-----------------------------|------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| -u or --saic-user           | SAIC_USER                    | SAIC user name - **required**                                                                                                                                                       |
| -p or --saic-password       | SAIC_PASSWORD                | SAIC password - **required**                                                                                                                                                        |
| --saic-phone-country-code   | SAIC_PHONE_COUNTRY_CODE      | Phone country code, used if the username is not an email address                                                                                                                    |
| --saic-rest-uri             | SAIC_REST_URI                | SAIC API URI. Default is the European Production endpoint: https://gateway-mg-eu.soimt.com/api.app/v1/                                                                              |
| --saic-region               | SAIC_REGION                  | SAIC API region. Default is eu.                                                                                                                                                     |
| --saic-tenant-id            | SAIC_TENANT_ID               | SAIC API tenant ID. Default is 459771.                                                                                                                                              |
| --saic-relogin-delay        | SAIC_RELOGIN_DELAY           | The gateway detects logins from other devices (e.g. the iSMART app). It then pauses it's activity for 900 seconds (default value). The delay can be configured with this parameter. |
| --messages-request-interval | MESSAGES_REQUEST_INTERVAL    | The interval for retrieving messages in seconds. Default is 60 seconds.                                                                                                             |
| --battery-capacity-mapping  | BATTERY_CAPACITY_MAPPING     | Mapping of VIN to full battery capacity. Multiple mappings can be provided separated by ',' Example: LSJXXXX=54.0,LSJYYYY=64.0                                                      |
| --charge-min-percentage     | CHARGE_MIN_PERCENTAGE        | How many % points we should try to refresh the charge state. 1.0 by default                                                                                                         |
| --publish-raw-api-data      | PUBLISH_RAW_API_DATA_ENABLED | Publish raw SAIC API request/response to MQTT. Disabled (False) by default.                                                                                                         |

#### API Endpoints

The following are the known available endpoints:

| SAIC_REST_URI                               | SAIC_REGION | Notes                                                                                                                                |
|---------------------------------------------|-------------|--------------------------------------------------------------------------------------------------------------------------------------|
| https://gateway-mg-au.soimt.com/api.app/v1/ | au          | This endpoint is not used by the iSmart app for Australia and New Zealand but has been tested and proven to work in these countries. |
| https://gateway-mg-eu.soimt.com/api.app/v1/ | eu          |                                                                                                                                      |

### MQTT Broker

| CMD param           | ENV variable     | Description                                                                                                                                                                                          |
|---------------------|------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| -m or --mqtt-uri    | MQTT_URI         | URI to the MQTT Server. TCP: tcp://mqtt.eclipseprojects.io:1883, WebSocket: ws://mqtt.eclipseprojects.io:9001 or TLS: tls://mqtt.eclipseprojects.io:8883 - Leave it empty to disable MQTT connection |
| --mqtt-server-cert  | MQTT_SERVER_CERT | Path to the server certificate authority file in PEM format is required for TLS                                                                                                                      |
| --mqtt-user         | MQTT_USER        | MQTT user name                                                                                                                                                                                       |
| --mqtt-password     | MQTT_PASSWORD    | MQTT password                                                                                                                                                                                        |
| --mqtt-client-id    | MQTT_CLIENT_ID   | MQTT Client Identifier. Defaults to saic-python-mqtt-gateway.                                                                                                                                        |
| --mqtt-topic-prefix | MQTT_TOPIC       | Provide a custom MQTT prefix to replace the default: saic                                                                                                                                            |
|                     | MQTT_LOG_LEVEL   | Log level of the MQTT Client: INFO (default), use DEBUG for detailed output, use CRITICAL for no output, [more info](https://docs.python.org/3/library/logging.html#levels)                          |

### Home Assistant Integration

| CMD param             | ENV variable         | Description                                                                                                                                                                         |
|-----------------------|----------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| --ha-discovery        | HA_DISCOVERY_ENABLED | Home Assistant auto-discovery is enabled (True) by default. It can be disabled (False) with this parameter.                                                                         |
| --ha-discovery-prefix | HA_DISCOVERY_PREFIX  | The default MQTT prefix for Home Assistant auto-discovery is 'homeassistant'. Another prefix can be configured with this parameter                                                  |
| --ha-show-unavailable | HA_SHOW_UNAVAILABLE  | Show entities as Unavailable in Home Assistant when car polling fails. Enabled (True) by default. Can be disabled, to retain the pre 0.6.x behaviour, but do that at your own risk. |

### A Better Route Planner (ABRP) integration

Telemetry data from your car can be provided to [ABRP](https://abetterrouteplanner.com/). **Be aware that this is not
done by default.** The data will be sent only if you provide the mapping of your vehicle identification number (VIN) to
an ABRP user token.

Those parameters can be used to allow the MQTT Gateway to send data to ABRP API

| CMD param               | ENV variable                  | Description                                                                                                                              |
|-------------------------|-------------------------------|------------------------------------------------------------------------------------------------------------------------------------------|
| --abrp-api-key          | ABRP_API_KEY                  | API key for the A Better Route Planner telemetry API. Default is the open source telemetry API key 8cfc314b-03cd-4efe-ab7d-4431cd8f2e2d. |
| --abrp-user-token       | ABRP_USER_TOKEN               | Mapping of VIN to ABRP User Token. Multiple mappings can be provided separated by ',' Example: LSJXXXX=12345-abcdef,LSJYYYY=67890-ghijkl |
| --publish-raw-abrp-data | PUBLISH_RAW_ABRP_DATA_ENABLED | Publish raw ABRP API request/response to MQTT. Disabled (False) by default.                                                              |

### OsmAnd Integration (e.g. Traccar)

Telemetry data from your car can be provided to a generic fleet tracking software supporting
the [OsmAnd](https://www.traccar.org/osmand/) protocol like [Traccar](https://www.traccar.org/)

Those parameters can be used to allow the MQTT Gateway to send data to an OsmAnd-compatibile server.

| CMD param                 | ENV variable                    | Description                                                                                                                                                                                  |
|---------------------------|---------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| --osmand-server-uri       | OSMAND_SERVER_URI               | The URL of your OsmAnd Server                                                                                                                                                                |
| --osmand-device-id        | OSMAND_DEVICE_ID                | Mapping of VIN to OsmAnd Device Id. Multiple mappings can be provided separated by ',' Example: LSJXXXX=12345-abcdef,LSJYYYY=67890-ghijkl. Defaults to use the car VIN as Device Id if unset |
| --publish-raw-osmand-data | PUBLISH_RAW_OSMAND_DATA_ENABLED | Publish raw ABRP OSMAND request/response to MQTT. Disabled (False) by default.                                                                                                               |

### OpenWB Integration

| CMD param                | ENV variable           | Description                                      |
|--------------------------|------------------------|--------------------------------------------------|
| --charging-stations-json | CHARGING_STATIONS_JSON | Custom charging stations configuration file name |

If your charging station also provides information over MQTT or if you somehow manage to publish information from your
charging station, the MQTT gateway can benefit from it. In addition, the MQTT gateway can provide the SoC to your
charging station.

An [openWB](https://openwb.de) charging station is capable of providing information over MQTT for instance. You just
need to provide the configuration in the file charging-stations.json. A sample configuration for two cars connected to
an openWB charging station would be the following.

Check-out the [sample file](examples\charging-stations.json.sample)

The key-value pairs in the JSON express the following:

| JSON key              | Description                                                                                       |
|-----------------------|---------------------------------------------------------------------------------------------------|
| chargeStateTopic      | topic indicating the charge state - **required**                                                  |
| chargingValue         | payload that indicates the charging - **required**                                                |
| socTopic              | topic where the gateway publishes the SoC for the charging station - optional                     |
| rangeTopic            | topic where the gateway publishes the range for the charging station - optional                   |
| chargerConnectedTopic | topic indicating that the vehicle is connected to the charging station - optional                 |
| chargerConnectedValue | payload that indicates that the charger is connected - optional                                   |
| vin                   | vehicle identification number to map the charging station information to a vehicle - **required** |

### Advanced settings

| CMD param | ENV variable | Description                                                                                                                                              |
|-----------|--------------|----------------------------------------------------------------------------------------------------------------------------------------------------------|
|           | LOG_LEVEL    | Log level: INFO (default), use DEBUG for detailed output, use CRITICAL for no output, [more info](https://docs.python.org/3/library/logging.html#levels) |

## Running the service

### From Command-line

To run the service from the command line you need to have Python version 3.12 or later.
Launch the MQTT gateway with the mandatory parametersn and, optionally, the url to the MQTT broker.

```
$ python ./mqtt_gateway.py -m tcp://my-broker-host:1883 -u <saic-user> -p <saic-pwd>
```

### In a docker container

Build the image yourself with the [Dockerfile](Dockerfile) or download the image
from [docker hub](https://hub.docker.com/r/saicismartapi/saic-python-mqtt-gateway).

#### Building the docker image

```
$ docker build -t saic-mqtt-gateway .
```

There is a [docker compose file](docker-compose.yml) that shows how to set up the service.

## Commands over MQTT

The MQTT Gateway subscribes to MQTT topics where it is listening for commands. Every topic in the table below starts
with the default vehicle prefix: `saic/<saic_user>/vehicles/<vehicle_id>`

| Topic                                    | Value range                                          | Description                                                                                                                                                                                                                           |
|------------------------------------------|------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| /drivetrain/hvBatteryActive/set          | true/false                                           | Overwrite high voltage battery state (Don't touch this unless you know what you are doing!)                                                                                                                                           |
| /drivetrain/charging/set                 | true/false                                           | Start (true) or stop (false) charging. Stopping works fine, starting is not so reliable yet                                                                                                                                           |
| /drivetrain/socTarget/set                | [40,50,60,70,80,90,100]                              | Target SoC in percent. Only values from the defined value range are valid.                                                                                                                                                            |
| /drivetrain/chargingSchedule/set         | JSON Payload. Fields are startTime, endTime and mode | Set the charging schedule.                                                                                                                                                                                                            |
| /drivetrain/chargeCurrentLimit/set       | [6A,8A,16A,MAX]                                      | Set the charge current limit in Ampere. Only values from the defined value range are valid.                                                                                                                                           |
| /drivetrain/batteryHeating/set           | true/false                                           | Start (true) or stop (false) battery heating. The car may refuse the command if it is deemed unnecessary                                                                                                                              |
| /drivetrain/batteryHeatingSchedule/set   | JSON Payload. Fields are startTime and mode          | Set the battery heating schedule. Mode can be either on or off                                                                                                                                                                        |
| /doors/boot/set                          | true/false                                           | Lock or unlock boot                                                                                                                                                                                                                   |
| /doors/locked/set                        | true/false                                           | Lock or unlock your car. This is not always working. It might take some time until it takes effect. Don't trust this feature. Use your car key!                                                                                       |
| /climate/remoteTemperature/set           | temperature                                          | Set A/C temperature                                                                                                                                                                                                                   |
| /climate/remoteClimateState/set          | on/off/front/blowingonly                             | Turn A/C on or off, activate A/C blowing (front) or blowing only (blowingonly)                                                                                                                                                        |
| /climate/heatedSeatsFrontLeftLevel/set   | 0-3 or 0-1 depending on model                        | Set heated seats level for the front left seat. Some cars have three levels while others just an on-off switch. 0 means OFF                                                                                                           |
| /climate/heatedSeatsFrontRightLevel/set  | 0-3 or 0-1 depending on model                        | Set heated seats level for the front right seat. Some cars have three levels while others just an on-off switch. 0 means OFF                                                                                                          |
| /climate/rearWindowDefrosterHeating/set  | on/off                                               | Turn rear window defroster heating on or off. This is not always working. It might take some time until it takes effect.                                                                                                              |
| /climate/frontWindowDefrosterHeating/set | on/off                                               | Turn front window defroster heating on or off                                                                                                                                                                                         |
| /refresh/mode/set                        | periodic/off/force                                   | The gateway queries the vehicle and charge status periodically after a vehicle start event has happened (default value: periodic. The periodic refresh can be switched off (value: off). A refresh can also be forced (value: force). |
| /refresh/period/active/set               | refresh interval (sec)                               | In case a vehicle start event has occurred, the gateway queries the status every 30 seconds (default value). The refresh interval can be modified with this topic.                                                                    |
| /refresh/period/inActive/set             | refresh interval (sec)                               | Vehicle and charge status are queried once per day (default value: 86400) independently from any event. Changing this to a lower value might affect the 12V battery of your vehicle. Be very careful!                                 |
| /refresh/period/afterShutdown/set        | refresh interval (sec)                               | After the vehicle has been shutdown, the gateway queries the status every 120 seconds (default value). The refresh interval can be modified with this topic.                                                                          |
| /refresh/period/inActiveGrace/set        | grace period (sec)                                   | After the vehicle has been shutdown, the gateway continues to query the state for 600 seconds (default value). The duration of this extended query period can be modified with this topic.                                            |
| /location/findMyCar/set                  | [activate,lights_only,horn_only,stop]                | Activate 'find my car' with lights and horn (activate), with lights only (lights_only), with horn only (horn_only) or deactivate it (stop).                                                                                           |

## Home Assistant auto-discovery

The gateway supports [Home Assistant MQTT discovery](https://www.home-assistant.io/integrations/mqtt#mqtt-discovery). It
publishes configuration information so that the vehicle appears as a MQTT device. This will save you a lot of
configuration effort since all the entities provided by the vehicle will automatically show-up in Home Assistant.
