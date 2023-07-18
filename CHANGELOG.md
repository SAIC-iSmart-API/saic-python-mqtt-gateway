# Change Log

## 0.3.0

### Added

* keep polling for 10 Minutes after engine stop to solve: detect car is charging #20
* battery target load
TODO: work on (remoteClimateState)[https://github.com/orgs/SAIC-iSmart-API/discussions/6#discussioncomment-5923522] related to  Feature request: A/C control #13

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
