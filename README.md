# SAIC MQTT Gateway

A service that queries the data from an MG iSMART account and publishes the data over MQTT.

MG iSMART is the connectivity system in your MG car (MG5, MG4, ZS...).

The implementation is based on the findings from the [SAIC-iSmart-API Documentation](https://github.com/SAIC-iSmart-API/documentation) project.

## Prerequisites

* You have an iSMART account (can be created in the iSMART app)
* Your car needs to be registered to your account

## Configuration

Configuration parameters can be provided as command line parameters or environment variables (this is what you typically do when you run the service from a docker container).

| CMD param             | ENV variable         | Description                                                                                                                                                                          |
|-----------------------|----------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| -u or --saic-user     | SAIC_USER            | SAIC user name - **required**                                                                                                                                                        |
| -p or --saic-password | SAIC_PASSWORD        | SAIC password - **required**                                                                                                                                                         |
| -m or --mqtt-uri      | MQTT_URI             | URI to the MQTT Server. TCP: tcp://mqtt.eclipseprojects.io:1883 or WebSocket: ws://mqtt.eclipseprojects.io:9001 - **required**                                                       |
| --mqtt-user           | MQTT_USER            | MQTT user name                                                                                                                                                                       |
| --mqtt-password       | MQTT_PASSWORD        | MQTT password                                                                                                                                                                        |
| --mqtt-topic-prefix   | MQTT_TOPIC           | Provide a custom MQTT prefix to replace the default: saic                                                                                                                            |
| --saic-uri            | SAIC_URI             | SAIC URI. Default is the European Production endpoint: https://tap-eu.soimt.com                                                                                                      |
| --abrp-api-key        | ABRP_API_KEY         | API key for the A Better Route Planner telemetry API. Default is the open source telemetry API key 8cfc314b-03cd-4efe-ab7d-4431cd8f2e2d.                                             |
| --abrp-user-token     | ABRP_USER_TOKEN      | Mapping of VIN to ABRP User Token. Multiple mappings can be provided seperated by ',' Example: LSJXXXX=12345-abcdef,LSJYYYY=67890-ghijkl                                             |
| --openwb-lp-map       | OPENWB_LP_MAP        | Mapping of VIN to openWB charging point. Multiple mappings can be provided seperated by ',' Example: 1=LSJXXXX,2=LSJYYYY                                                             |
| --saic-relogin-delay  | SAIC_RELOGIN_DELAY   | The gateway detects logins from other devices (e.g. the iSMART app). It then pauses it's activity for 900 seconds (default value). The delay can be configured with this parameter.  |
| --ha-discovery        | HA_DISCOVERY_ENABLED | Home Assistant auto-discovery is enabled (True) by default. It can be disabled (False) with this parameter.                                                                          |
| --ha-discovery-prefix | HA_DISCOVERY_PREFIX  | The default MQTT prefix for Home Assistant auto-discovery is 'homeassistant'. Another prefix can be configured with this parameter                                                   |
|                       | LOG_LEVEL            | Log level: INFO (default), use DEBUG for detailed output, use CRITICAL for no ouput, [more info](https://docs.python.org/3/library/logging.html#levels)                              |

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

## openWB integration

The state-of-charge (SoC) can be provided over MQTT to an [openWB wallbox](https://openwb.de). To activate this, you need to provide the Mapping of VIN to openWB charging point. With this information the gateway can also detect that the vehicle is charging.

Just configure the MQTT gateway to connect to the MQTT broker which is running on your openWB and enable SoC over MQTT in the openWB.

The openWB can also connect to an external MQTT broker. However, this connection needs to be secured with TLS so that messages are not exchanged in clear text. Since the MQTT gateway does not yet support secured MQTT connections, it won't be possible to use a third-party broker.

## A Better Route Planner (ABRP) integration

Telemetry data from your car can be provided to [ABRP](https://abetterrouteplanner.com/). **Be aware that this is not done by default.** The data will be sent only if you provide the mapping of your vehicle identification number (VIN) to an ABRP user token.

## Commands over MQTT

The MQTT Gateway subscribes to MQTT topics where it is listening for commands.

| Topic                                        | Value range              | Description                                                                                                                                                                                                                           |
|----------------------------------------------|--------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| <vp>/drivetrain/hvBatteryActive/set          | true/false               | Overwrite high voltage battery state (Don't touch this unless you know what you are doing!)                                                                                                                                           |
| <vp>/drivetrain/charging/set                 | true/false               | Start (true) or stop (false) charging. Stopping works fine, starting is not so reliable yet                                                                                                                                           |
| <vp>/climate/remoteTemperature/set           | temperature              | Set A/C temperature                                                                                                                                                                                                                   |
| <vp>/climate/remoteClimateState/set          | on/off/front/blowingOnly | Turn A/C on or off, activate A/C blowing (front) or blowing only (blowingOnly)                                                                                                                                                        |
| <vp>/doors/boot/set                          | true/false               | Lock or unlock boot                                                                                                                                                                                                                   |
| <vp>/doors/locked/set                        | true/false               | Lock or unlock your car. This is not always working. It might take some time until it takes effect. Don't trust this feature. Use your car key!                                                                                       |
| <vp>/climate/rearWindowDefrosterHeating/set  | on/off                   | Turn rear window defroster heating on or off. This is not always working. It might take some time until it takes effect.                                                                                                              |
| <vp>/climate/frontWindowDefrosterHeating/set | on/off                   | Turn front window defroster heating on or off                                                                                                                                                                                         |
| <vp>/drivetrain/socTarget/set                | [40,50,60,70,80,90,100]  | Target SoC in percent. Only values from the defined value range are valid.                                                                                                                                                            |
| <vp>/refresh/mode/set                        | periodic/off/force       | The gateway queries the vehicle and charge status periodically after a vehicle start event has happened (default value: periodic. The periodic refresh can be switched off (value: off). A refresh can also be forced (value: force). |
| <vp>/refresh/period/active/set               | refresh interval (sec)   | In case a vehicle start event has occurred, the gateway queries the status every 30 seconds (default value). The refresh interval can be modified with this topic.                                                                    |
| <vp>/refresh/period/inActive/set             | refresh interval (sec)   | Vehicle and charge status are queried once per day (default value: 86400) independently from any event. Changing this to a lower value might affect the 12V battery of your vehicle. Be very careful!                                 |
| <vp>/refresh/period/afterShutdown/set        | refresh interval (sec)   | After the vehicle has been shutdown, the gateway queries the status every 120 seconds (default value). The refresh interval can be modified with this topic.                                                                          |
| <vp>/refresh/period/inActiveGrace/set        | grace period (sec)       | After the vehicle has been shutdown, the gateway continues to query the state for 600 seconds (default value). The duration of this extended query period can be modified with this topic.                                            |

default vehicle prefix (vp): saic/<saic_user>/vehicles/<vehicle_id>

## Home Assistant auto-discovery

The gateway supports [Home Assistant MQTT discovery](https://www.home-assistant.io/integrations/mqtt#mqtt-discovery). It publishes configuration information so that the vehicle appears as a MQTT device. This will save you a lot of configuration effort since all the entities provided by the vehicle will automatically show-up in Home Assistant.
