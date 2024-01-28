# Change Log

## 0.5.0

### Changed

* Switch to saic-python-client-ng library (New SAIC API)
* blowing only command fixed

## 0.4.7

### Changed

* Whenever a chargingValue is received that is different from the last received value, a forced refresh is performed
* The socTopic is an optional field in the charging station configuration

## 0.4.6

### Fixed

* Detection of battery type
* Remove special characters from username to generate valid MQTT topics
* Setting ha_discovery_enabled to False had no effect
* Docker image based on python:3.11-slim
* Force refresh by charging station only if charging value has changed
* MQTT connection error logging 
* Front window heating enables "Blowing only"

## 0.4.5

### Fixed

* Binary string decoding issue fixed in saic-python-client 1.6.5

## 0.4.4

### Fixed

* Error message decoding issue fixed in saic-python-client 1.6.4

## 0.4.3

### Fixed

* Previous fix corrects dispatcher message size for V2 messages. Now it is also fixed for V1 messages.

## 0.4.2

### Fixed

* Previous fix works only for messages without application data. Those are typically error messages that are provided with wrong dispatcher message size

## 0.4.1

### Fixed

* Calculate dispatcher message size and use the calculated value if it differs from the provided API value

## 0.4.0

### Added

* Control charge current limit
* Dynamic refresh period during charging
* Force polling around scheduled charging start
* Further A/C enhancements
* Generic charging station integration (OPENWB_LP_MAP argument is deprecated now)
* TLS support

## 0.3.0

### Added

* Keep polling for a configurable amount of time after the vehicle has been shutdown
* Battery (SoC) target load
* Start/Stop charging
* Enhanced A/C control
* Turn off message requests when refresh mode is off
* Home Assistant auto-discovery

### Fixed

* Vehicle and charging status updates stop after a while
* Inconsistent topic name for battery management data (BMS) removed

## 0.2.4

### Added

* docker support for architecture linux/arm/v7

## 0.2.3

### Added

* Using new saic-ismart-client (version 1.3.0)
* Feature: transmit ABRP data even if we have no GPS data

### Fixed

* empty environment variables are ignored
* Driving detection fixed

## 0.2.2

Vehicle control commands are finally working

### Added

* Turn front window defroster heating on or off
* Turn A/C on or off
* Configurable re-login delay
* Using new saic-ismart-client (version 1.2.6)
* Environment variable to configure log level

### Fixed
* environment variable overwrites the predefined default value

## 0.2.1

### Added

* MQTT commands documented in README.md

### Changed

* Wait 15 seconds (average SMS delivery time) for the vehicle to wake up
* Using new saic-ismart-client (version 1.1.7)
* Improved parsing for configuration value mappings

### Fixed

* Make force command more reliable
