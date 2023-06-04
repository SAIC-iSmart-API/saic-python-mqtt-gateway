# Change Log

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
