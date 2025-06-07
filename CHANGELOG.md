# Change Log

## 0.9.5

## What's Changed
* Extend ZS EV battery capacity to high trim and long range models by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/339

## 0.9.4

## What's Changed
* Introduce armv7 support instead of armv6 by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/336

## 0.9.3

## What's Changed
* Restore phone login by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/334

## 0.9.2

### What's Changed
* Migrated Last Charge SoC kWh sensor to 'measurement' state_class

## 0.9.1

### What's Changed
* Fixed a bug in message processing when no messages where found on SAIC servers

## 0.9.0 

### What's Changed
* Compatibiltity with the latest mobile app release
* #292: Push HA discovery again when HA connects to broker by @krombel in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/294
* add random delay before pushing discovery by @krombel in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/295
* #296: Detect charging from BMS instead of car state by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/298
* Mark 'Last Charge SoC kWh' in HA as a TOTAL_INCRESING sensor so that it can be used in Energy Dashboard by @nanomad
* Expose journey ID to Home Assistant by @nanomad
* Internally mark the car as "shutdown" only after the car state changes.
This avoids looking for a "charging started" event as soon as the charging is completed by @nanomad
* Keep retrying initial login by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/319
* Publish window status only if mileage is reported properly by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/320

### New Contributors
* @krombel made their first contribution in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/294

**Full Changelog**: https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/compare/0.7.1...0.9.0

## 0.7.1

## What's changed
* #287: Gracefully handle cases where the messages api returns no data by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/290

## 0.7.0

## What's Changed
* Fixed many stability issues with the login process
* Fixed battery capacity calculation for newer MG4 variants
* Updated README.md with SAIC API Endpoints section by @karter16 in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/260
* Add suffix to battery heating stop reason topic to allow discriminate it from battery heating topic by @pakozm in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/253
* Gracefully handle scenarios where we don't know the real battery capcity of the car by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/261
* Initial support for fossil fuel cars like MG3 Hybrid by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/262
* Move relogin logic to the MQTT Gateway instead of the API library by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/265
* [WIP] Expose Find by car functionality by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/266
* Fix #73: Allow running the gateway without an MQTT connection by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/267
* Minor updates by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/268
* #283: Publish HA discovery once per car by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/284
* #279: Restore the original normalization rule by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/285

## New Contributors
* @karter16 made their first contribution in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/260
* @pakozm made their first contribution in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/253

**Full Changelog**: https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/compare/0.6.3...0.7.0

## 0.6.3

### What's changed

* Feat: try to recover SoC% from vehicle state if BMS is not responding by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/247
* Fix tests for drivetrain soc from vehicle state by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/248

## 0.6.2

### Fixed

* Fix charge_status.bmsPackCrntV check for ABRP integration by @nanomad in #234
* Handle unreliable 3d fix information, fall back to reported altitude by @nanomad in #235
* Make message handling more robust by @nanomad in #237
* Process MQTT messages after we receivied a list of cars by @nanomad in #238
* ABRP-1537: Drop future timestamps when pushing data to ABRP by @nanomad in #242

### What's changed

* Try to extract remaining electric range from either car or BMS by @nanomad in #236

## 0.6.1

### Fixed

* Charging power and current showing 0 on models different from MG4
* HA: Heading sensor is now recorded with a unit of measure

### What's Changed

* HA: Allow overriding the default "Unavailable" behaviour via HA_SHOW_UNAVAILABLE by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/220
* mplement missing hash function for HaCustomAvailabilityEntry by @nanomad in #222
* Add IGNORE_BMS_CURRENT_VALIDATION and decode API responses by @nanomad in #225
* Drop IGNORE_BMS_CURRENT_VALIDATION experiment, just mark current as invalid if bmsPackCrntV is 1 (None or 0 means valid) by @nanomad in #226
* Add Unit of measure to heading sensor. by @nanomad in #228

## 0.6.0

### Import upgrade notes

Please note that 0.6.0 will more aggresively mark the vehicle as offline on Home Assitant in order to avoid providing false
information to the user. When the vehicle is "offline" no commands can be sent to it, except for a force refresh.

### Added

* Support for openWB software version 2.0 by @tosate in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/172
* Expose power usage stats by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/178
* Added support for cable lock and unlock by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/188
* Exponential backoff during polling failures by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/193
* Expose last charge start and end times by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/201
* Add sensors for current journey and OBC data by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/205
* Side lights detection by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/210

### Fixed

* Battery capacity for MG ZS EV Standard 2021 by @tosate in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/160
* Add battery capacity for MG5 Maximum Range Luxury by @sfudeus in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/166
* Fix initial remote ac temp value by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/175
* Apply battery_capacity_correction_factor to lastChargeEndingPower by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/176
* Detect DRIVETRAIN_HV_BATTERY_ACTIVE when rear window heater is on by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/177
* Read electric estimated range from BMS and Car State as it gets reset during parking by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/181
* Compute charging refresh period based on charging power.  by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/183
* Re-introduce tests and run them every push by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/189
* Run CI on push and PR by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/190
* Mark car not available if polling fails by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/191
* Temporary fix: require just a vehicle state refresh to mark vehicle loop as completed by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/192
* Assume speed is 0.0 if we have no GPS data by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/196
* Fix Charging finished sensor by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/197
* Do not send invalid data to ABRP and MQTT by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/199
* Fix test data by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/200
* Data validation by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/204
* During charging, do not easily fall back on the active refresh period by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/206
* Fix BMS and Journey sensors by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/207
* Fix currentJourneyDistance scale factor by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/208
* GPS and Charging detection fixes by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/209
* Remove special characters from MQTT topics. by @tosate in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/214
* Avoid processing vehicle status updates if the server clock has drifted too much by @nanomad in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/211

### New Contributors
* @tosate made their first contribution in https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/pull/160

**Full Changelog**: https://github.com/SAIC-iSmart-API/saic-python-mqtt-gateway/compare/0.5.15...0.6.0

## 0.5.15

### Added

* Battery capacity for MG4 Trophy Extended Range
* Battery capacity for MG5 SR Comfort

## 0.5.10

### Added

* MQTT: Add support for scheduled battery heating. Payload is JSON with startTime and mode (on or off)
* HA: Expose scheduled battery heating
* HA: Expose some switches as sensors as well to ease automations

## 0.5.9

### Added

* MQTT: Add support for battery heating. True means ON, False means OFF
* HA: Expose battery heating as an ON-OFF switch

## 0.5.8

### Added

* MQTT: Add support for heated seats control on both front left and front right seats. Values range from 0-3 on some
  models, 0-1 on others. 0 means OFF
* HA: Expose heated seats control as either a select with 4 states (OFF, LOW, MEDIUM, HIGH) or as a ON-OFF switch
  depending on the reported car feature set

## 0.5.7

### Fixed

* Align some vehicle control commands to their actual behavior on the official app
* Door closing command should be more reliable now

### Added

* The new option `SAIC_PHONE_COUNTRY_CODE` can be used to specify the country code for the phone number used to login

## 0.5.2

### Fixed

* Gateway was not logging-in properly after a logout

### Changed

* Config option `SAIC_REST_URI` now points to the new production API endpoint by default

### Added

* Config option `SAIC_REGION` is used to select the new API region
* Config option `SAIC_TENANT_ID` is used to select the new API tenant

Both values default to the EU instance production values

### Removed

* Drop config option `SAIC_URI` as it is no longer relevant

## 0.5.1

### Fixed

* Typo in check_for_new_messages() fixed

### Added

* Configurable messages-request-interval

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

* Previous fix works only for messages without application data. Those are typically error messages that are provided
  with wrong dispatcher message size

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
