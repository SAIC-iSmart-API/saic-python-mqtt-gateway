# SAIC MQTT Gateway

A service that queries the data from an MG iSMART account and publishes the data over MQTT.

MG iSMART is the connectivity system in your MG car (MG5, MG4, ZS...).

The implementation is based on the findings from the [SAIC-iSmart-API Documentation](https://github.com/SAIC-iSmart-API/documentation) project.

## Prerequisites

* You have an iSMART account (can be created in the iSMART app)
* Your car needs to be registered to your account

## Configuration

Configuration parameters can be provided as command line parameters or environment variables (this is what you typically do when you run the service from a docker container).

| CMD param             | ENV variable    | Description                                                                                                                              |
|-----------------------|-----------------|------------------------------------------------------------------------------------------------------------------------------------------|
| -m or --mqtt-uri      | MQTT_URI        | URI to the MQTT Server. TCP: tcp://mqtt.eclipseprojects.io:1883 or WebSocket: ws://mqtt.eclipseprojects.io:9001 - **required**           |
| --mqtt-user           | MQTT_USER       | MQTT user name                                                                                                                           |
| --mqtt-password       | MQTT_PASSWORD   | MQTT password                                                                                                                            |
| --mqtt-topic-prefix   | MQTT_TOPIC      | Provide a custom MQTT prefix to replace the default: saic                                                                                |
| -u or --saic-user     | SAIC_USER       | SAIC user name - **required**                                                                                                            |
| -p or --saic-password | SAIC_PASSWORD   | SAIC password - **required**                                                                                                             |
| --abrp-api-key        | ABRP_API_KEY    | API key for the A Better Route Planner telemetry API. Default is the open source telemetry API key 8cfc314b-03cd-4efe-ab7d-4431cd8f2e2d.  |
| --abrp-user-token     | ABRP_USER_TOKEN | Mapping of VIN to ABRP User Token. Multiple mappings can be provided seperated by ',' Example: LSJXXXX=12345-abcdef,LSJYYYY=67890-ghijkl |
| --openwb-lp-map       | OPENWB_LP_MAP   | Mapping of VIN to openWB charging point. Multiple mappings can be provided seperated by ',' Example: 1=LSJXXXX,2=LSJYYYY                 |


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
