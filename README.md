# SAIC MQTT Gateway

A service that queries the data from an MG iSMART account and publishes the data over MQTT.

MG iSMART is the connectivity system in your MG car (MG5, MG4, ZS...).

The implementation is based on the findings from the [SAIC-iSmart-API Documentation](https://github.com/SAIC-iSmart-API/documentation) project.

## Prerequisites

* You have an iSMART account (can be created in the iSMART app)
* Your car needs to be registered to your account

## Configuration

Configuration parameters can be provided as command line parameters or environment variables (this is what you typically do when you run the service from a docker container).

| CMD param                  | ENV variable             | Description                                                                                                                                                                         |
|----------------------------|--------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| -u or --saic-user          | SAIC_USER                | SAIC user name - **required**                                                                                                                                                       |
| -p or --saic-password      | SAIC_PASSWORD            | SAIC password - **required**                                                                                                                                                        |
| -m or --mqtt-uri           | MQTT_URI                 | URI to the MQTT Server. TCP: tcp://mqtt.eclipseprojects.io:1883, WebSocket: ws://mqtt.eclipseprojects.io:9001 or TLS: tls://mqtt.eclipseprojects.io:8883 - **required**             |
| --mqtt-server-cert         | MQTT_SERVER_CERT         | Path to the server certificate authority file in PEM format is required for TLS                                                                                                     |
| --mqtt-user                | MQTT_USER                | MQTT user name                                                                                                                                                                      |
| --mqtt-password            | MQTT_PASSWORD            | MQTT password                                                                                                                                                                       |
| --mqtt-client-id           | MQTT_CLIENT_ID           | MQTT Client Identifier. Defaults to saic-python-mqtt-gateway.                                                                                                                       |
| --mqtt-topic-prefix        | MQTT_TOPIC               | Provide a custom MQTT prefix to replace the default: saic                                                                                                                           |
| --saic-uri                 | SAIC_URI                 | SAIC URI. Default is the European Production endpoint: https://tap-eu.soimt.com                                                                                                     |
| --abrp-api-key             | ABRP_API_KEY             | API key for the A Better Route Planner telemetry API. Default is the open source telemetry API key 8cfc314b-03cd-4efe-ab7d-4431cd8f2e2d.                                            |
| --abrp-user-token          | ABRP_USER_TOKEN          | Mapping of VIN to ABRP User Token. Multiple mappings can be provided separated by ',' Example: LSJXXXX=12345-abcdef,LSJYYYY=67890-ghijkl                                            |
| --battery-capacity-mapping | BATTERY_CAPACITY_MAPPING | Mapping of VIN to full battery capacity. Multiple mappings can be provided separated by ',' Example: LSJXXXX=54.0,LSJYYYY=64.0                                                      |
| --openwb-lp-map            | OPENWB_LP_MAP            | Mapping of VIN to openWB charging point. Multiple mappings can be provided separated by ',' Example: 1=LSJXXXX,2=LSJYYYY - **deprecated**                                           |
| --charging-stations-json   | CHARGING_STATIONS_JSON   | Custom charging stations configuration file name                                                                                                                                    |
| --saic-relogin-delay       | SAIC_RELOGIN_DELAY       | The gateway detects logins from other devices (e.g. the iSMART app). It then pauses it's activity for 900 seconds (default value). The delay can be configured with this parameter. |
| --ha-discovery             | HA_DISCOVERY_ENABLED     | Home Assistant auto-discovery is enabled (True) by default. It can be disabled (False) with this parameter.                                                                         |
| --ha-discovery-prefix      | HA_DISCOVERY_PREFIX      | The default MQTT prefix for Home Assistant auto-discovery is 'homeassistant'. Another prefix can be configured with this parameter                                                  |
|                            | LOG_LEVEL                | Log level: INFO (default), use DEBUG for detailed output, use CRITICAL for no output, [more info](https://docs.python.org/3/library/logging.html#levels)                            |
|                            | MQTT_LOG_LEVEL           | Log level of the MQTT Client: INFO (default), use DEBUG for detailed output, use CRITICAL for no output, [more info](https://docs.python.org/3/library/logging.html#levels)         |

### Charging Station Configuration

If your charging station also provides information over MQTT or if you somehow manage to publish information from your charging station, the MQTT gateway can benefit from it. In addition, the MQTT gateway can provide the SoC to your charging station.

An [openWB](https://openwb.de) charging station is capable of providing information over MQTT for instance. You just need to provide the configuration in the file charging-stations.json. A sample configuration for two cars connected to an openWB charging station would be the following.

Check-out the [sample file](charging-stations.json.sample)

The key-value pairs in the JSON express the following: 

| JSON key              | Description                                                                                       |
|-----------------------|---------------------------------------------------------------------------------------------------|
| chargeStateTopic      | topic indicating the charge state - **required**                                                  |
| chargingValue         | payload that indicates the charging - **required**                                                |
| socTopic              | topic where the gateway publishes the SoC for the charging station - **required**                 |
| chargerConnectedTopic | topic indicating that the vehicle is connected to the charging station - optional                 |
| chargerConnectedValue | payload that indicates that the charger is connected - optional                                   |
| vin                   | vehicle identification number to map the charging station information to a vehicle - **required** |

## Running the service

### From Command-line

To run the service from the command line you need to have Python version 3.10 or later.
Launch the MQTT gateway with the mandatory parameters.

```
$ python ./mqtt_gateway.py -m tcp://my-broker-host:1883 -u <saic-user> -p <saic-pwd>
```

### In a docker container

Build the image yourself with the [Dockerfile](Dockerfile) or download the image from [docker hub](https://hub.docker.com/r/saicismartapi/saic-python-mqtt-gateway).

#### Building the docker image
```
$ docker build -t saic-mqtt-gateway .
```

There is a [docker compose file](docker-compose.yml) that shows how to set up the service.


## A Better Route Planner (ABRP) integration

Telemetry data from your car can be provided to [ABRP](https://abetterrouteplanner.com/). **Be aware that this is not done by default.** The data will be sent only if you provide the mapping of your vehicle identification number (VIN) to an ABRP user token.

## Commands over MQTT

The MQTT Gateway subscribes to MQTT topics where it is listening for commands. Every topic in the table below starts with the default vehicle prefix: `saic/<saic_user>/vehicles/<vehicle_id>`

| Topic                                    | Value range              | Description                                                                                                                                                                                                                           |
|------------------------------------------|--------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| /drivetrain/hvBatteryActive/set          | true/false               | Overwrite high voltage battery state (Don't touch this unless you know what you are doing!)                                                                                                                                           |
| /drivetrain/charging/set                 | true/false               | Start (true) or stop (false) charging. Stopping works fine, starting is not so reliable yet                                                                                                                                           |
| /climate/remoteTemperature/set           | temperature              | Set A/C temperature                                                                                                                                                                                                                   |
| /climate/remoteClimateState/set          | on/off/front/blowingOnly | Turn A/C on or off, activate A/C blowing (front) or blowing only (blowingOnly)                                                                                                                                                        |
| /doors/boot/set                          | true/false               | Lock or unlock boot                                                                                                                                                                                                                   |
| /doors/locked/set                        | true/false               | Lock or unlock your car. This is not always working. It might take some time until it takes effect. Don't trust this feature. Use your car key!                                                                                       |
| /climate/rearWindowDefrosterHeating/set  | on/off                   | Turn rear window defroster heating on or off. This is not always working. It might take some time until it takes effect.                                                                                                              |
| /climate/frontWindowDefrosterHeating/set | on/off                   | Turn front window defroster heating on or off                                                                                                                                                                                         |
| /drivetrain/socTarget/set                | [40,50,60,70,80,90,100]  | Target SoC in percent. Only values from the defined value range are valid.                                                                                                                                                            |
| /refresh/mode/set                        | periodic/off/force       | The gateway queries the vehicle and charge status periodically after a vehicle start event has happened (default value: periodic. The periodic refresh can be switched off (value: off). A refresh can also be forced (value: force). |
| /refresh/period/active/set               | refresh interval (sec)   | In case a vehicle start event has occurred, the gateway queries the status every 30 seconds (default value). The refresh interval can be modified with this topic.                                                                    |
| /refresh/period/inActive/set             | refresh interval (sec)   | Vehicle and charge status are queried once per day (default value: 86400) independently from any event. Changing this to a lower value might affect the 12V battery of your vehicle. Be very careful!                                 |
| /refresh/period/afterShutdown/set        | refresh interval (sec)   | After the vehicle has been shutdown, the gateway queries the status every 120 seconds (default value). The refresh interval can be modified with this topic.                                                                          |
| /refresh/period/inActiveGrace/set        | grace period (sec)       | After the vehicle has been shutdown, the gateway continues to query the state for 600 seconds (default value). The duration of this extended query period can be modified with this topic.                                            |

## Home Assistant auto-discovery

The gateway supports [Home Assistant MQTT discovery](https://www.home-assistant.io/integrations/mqtt#mqtt-discovery). It publishes configuration information so that the vehicle appears as a MQTT device. This will save you a lot of configuration effort since all the entities provided by the vehicle will automatically show-up in Home Assistant.
