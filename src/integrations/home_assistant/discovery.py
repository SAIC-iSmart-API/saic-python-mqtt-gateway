from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, override

from saic_ismart_client_ng.api.vehicle_charging import (
    ChargeCurrentLimitCode,
    ScheduledChargingMode,
)

import mqtt_topics
from integrations.home_assistant.availability import (
    HaCustomAvailabilityConfig,
    HaCustomAvailabilityEntry,
)
from integrations.home_assistant.base import HomeAssistantDiscoveryBase
from integrations.home_assistant.utils import decode_as_utf8, snake_case
from publisher.mqtt_publisher import MqttPublisher
from vehicle import RefreshMode, VehicleState

if TYPE_CHECKING:
    from configuration import Configuration
    from vehicle_info import VehicleInfo

LOG = logging.getLogger(__name__)


class HomeAssistantDiscovery(HomeAssistantDiscoveryBase):
    def __init__(
        self,
        vehicle_state: VehicleState,
        vin_info: VehicleInfo,
        configuration: Configuration,
    ) -> None:
        self.__vehicle_state = vehicle_state
        self.__vin_info = vin_info
        self.__discovery_prefix = configuration.ha_discovery_prefix
        self.__system_availability = HaCustomAvailabilityEntry(
            topic=self.__get_system_topic(mqtt_topics.INTERNAL_LWT)
        )
        if configuration.ha_show_unavailable:
            self.__vehicle_availability = HaCustomAvailabilityEntry(
                topic=self.__get_vehicle_topic(mqtt_topics.AVAILABLE)
            )
        else:
            self.__vehicle_availability = self.__system_availability
        self.__system_availability_config = HaCustomAvailabilityConfig(
            rules=[self.__system_availability]
        )
        self.__standard_availability_config = HaCustomAvailabilityConfig(
            rules=[self.__system_availability, self.__vehicle_availability]
        )
        self.published = False

    def publish_ha_discovery_messages(self, *, force: bool = False) -> None:
        if not self.__vehicle_state.is_complete():
            LOG.warning(
                "Skipping Home Assistant discovery messages as vehicle state is not yet complete"
            )
            return

        if self.published and not force:
            LOG.debug(
                "Skipping Home Assistant discovery messages as it was already published"
            )
            return

        self.__publish_ha_discovery_messages_real()
        self.published = True

    def __publish_ha_discovery_messages_real(self) -> None:
        LOG.debug("Publishing Home Assistant discovery messages")

        # Gateway Control
        self.__publish_gateway_sensors()

        self._publish_sensor(
            mqtt_topics.INFO_LAST_MESSAGE_CONTENT,
            "Last car message",
            enabled=False,
            entity_category="diagnostic",
            custom_availability=self.__system_availability_config,
        )

        self.__publish_climate_sensors()

        # Complex sensors
        self.__publish_scheduled_charging()
        self.__publish_scheduled_battery_heating()

        # Switches
        self._publish_switch(mqtt_topics.DRIVETRAIN_CHARGING, "Charging")
        self._publish_switch(
            mqtt_topics.DRIVETRAIN_BATTERY_HEATING,
            "Battery heating",
            icon="mdi:heat-wave",
        )
        self.__publish_windows_sensors()

        # Locks
        self.__publish_doors_sensors()

        self._publish_lock(
            mqtt_topics.DRIVETRAIN_CHARGING_CABLE_LOCK,
            "Charging Cable Lock",
            icon="mdi:lock",
        )

        # Target SoC
        self._publish_number(
            mqtt_topics.DRIVETRAIN_SOC_TARGET,
            "Target SoC",
            enabled=self.__vin_info.supports_target_soc,
            device_class="battery",
            unit_of_measurement="%",
            icon="mdi:battery-charging-70",
            mode="slider",
            min_value=40,
            max_value=100,
            step=10,
        )
        options = [
            m.limit
            for m in ChargeCurrentLimitCode
            if m != ChargeCurrentLimitCode.C_IGNORE
        ]
        self._publish_select(
            mqtt_topics.DRIVETRAIN_CHARGECURRENT_LIMIT,
            "Charge current limit",
            options,
            entity_category=None,
            enabled=True,
            value_template="{{ value }}",
            command_template="{{ value }}",
            icon="mdi:current-ac",
            custom_availability=None,
        )

        # Standard sensors
        self._publish_sensor(
            mqtt_topics.DRIVETRAIN_SOC,
            "SoC",
            device_class="battery",
            state_class="measurement",
            unit_of_measurement="%",
        )
        self._publish_sensor(
            mqtt_topics.DRIVETRAIN_SOC_KWH,
            "SoC_kWh",
            device_class="ENERGY_STORAGE",
            state_class="measurement",
            unit_of_measurement="kWh",
            icon="mdi:battery-charging-70",
        )
        self._publish_sensor(
            mqtt_topics.DRIVETRAIN_TOTAL_BATTERY_CAPACITY,
            "Total Battery Capacity",
            entity_category="diagnostic",
            device_class="ENERGY_STORAGE",
            state_class="measurement",
            unit_of_measurement="kWh",
            icon="mdi:battery-high",
        )
        self._publish_sensor(
            mqtt_topics.DRIVETRAIN_LAST_CHARGE_ENDING_POWER,
            "Last Charge SoC kWh",
            device_class="ENERGY_STORAGE",
            state_class="measurement",
            unit_of_measurement="kWh",
            icon="mdi:battery-charging-70",
        )
        self._publish_sensor(
            mqtt_topics.DRIVETRAIN_POWER_USAGE_SINCE_LAST_CHARGE,
            "Energy Usage Since Last Charge",
            enabled=False,
            device_class="ENERGY_STORAGE",
            state_class="measurement",
            unit_of_measurement="kWh",
            icon="mdi:battery-charging-70",
        )
        self._publish_sensor(
            mqtt_topics.DRIVETRAIN_POWER_USAGE_OF_DAY,
            "Energy Usage of the Day",
            enabled=False,
            device_class="ENERGY_STORAGE",
            state_class="measurement",
            unit_of_measurement="kWh",
            icon="mdi:battery-charging-70",
        )

        self._publish_sensor(
            mqtt_topics.DRIVETRAIN_REMAINING_CHARGING_TIME,
            "Remaining charging time",
            device_class="duration",
            state_class="measurement",
            unit_of_measurement="s",
        )
        self._publish_sensor(
            mqtt_topics.DRIVETRAIN_REMAINING_CHARGING_TIME,
            "Charging finished",
            device_class="timestamp",
            value_template="{{ (now() + timedelta(seconds = value | int)).isoformat() }}",
            custom_availability=HaCustomAvailabilityConfig(
                rules=[
                    self.__system_availability,
                    self.__vehicle_availability,
                    HaCustomAvailabilityEntry(
                        topic=self.__get_vehicle_topic(
                            mqtt_topics.DRIVETRAIN_REMAINING_CHARGING_TIME
                        ),
                        template="{{ 'online' if (value | int) > 0 else 'offline' }}",
                    ),
                ]
            ),
        )
        self._publish_sensor(
            mqtt_topics.DRIVETRAIN_CHARGING_LAST_START,
            "Last Charge Start Time",
            device_class="timestamp",
            icon="mdi:clock-start",
            value_template="{{ value | int | timestamp_utc }}",
            custom_availability=HaCustomAvailabilityConfig(
                rules=[
                    self.__system_availability,
                    self.__vehicle_availability,
                    HaCustomAvailabilityEntry(
                        topic=self.__get_vehicle_topic(
                            mqtt_topics.DRIVETRAIN_CHARGING_LAST_START
                        ),
                        template="{{ 'online' if (value | int) > 0 else 'offline' }}",
                    ),
                ]
            ),
        )
        self._publish_sensor(
            mqtt_topics.DRIVETRAIN_CHARGING_LAST_END,
            "Last Charge End Time",
            device_class="timestamp",
            icon="mdi:clock-end",
            value_template="{{ value | int | timestamp_utc }}",
            custom_availability=HaCustomAvailabilityConfig(
                rules=[
                    self.__system_availability,
                    self.__vehicle_availability,
                    HaCustomAvailabilityEntry(
                        topic=self.__get_vehicle_topic(
                            mqtt_topics.DRIVETRAIN_CHARGING_LAST_END
                        ),
                        template="{{ 'online' if (value | int) > 0 else 'offline' }}",
                    ),
                ]
            ),
        )
        self._publish_sensor(
            mqtt_topics.DRIVETRAIN_CHARGING_TYPE,
            "Charging Mode",
            enabled=False,
            entity_category="diagnostic",
        )
        self._publish_sensor(
            mqtt_topics.BMS_CHARGE_STATUS,
            "BMS Charge Status",
            enabled=False,
            entity_category="diagnostic",
        )
        self._publish_sensor(
            mqtt_topics.DRIVETRAIN_MILEAGE,
            "Mileage",
            device_class="distance",
            state_class="total_increasing",
            unit_of_measurement="km",
        )
        self._publish_sensor(
            mqtt_topics.DRIVETRAIN_MILEAGE_OF_DAY,
            "Mileage of the day",
            enabled=False,
            device_class="distance",
            state_class="total_increasing",
            unit_of_measurement="km",
        )
        self._publish_sensor(
            mqtt_topics.DRIVETRAIN_MILEAGE_SINCE_LAST_CHARGE,
            "Mileage since last charge",
            enabled=False,
            device_class="distance",
            state_class="total_increasing",
            unit_of_measurement="km",
        )
        self._publish_sensor(
            mqtt_topics.DRIVETRAIN_CURRENT_JOURNEY,
            "Mileage of journey",
            enabled=False,
            device_class="distance",
            state_class="total_increasing",
            unit_of_measurement="km",
            value_template='{{ value_json["distance"] | int(0) }}',
        )
        self._publish_sensor(
            mqtt_topics.DRIVETRAIN_CURRENT_JOURNEY,
            "Identifier of journey",
            enabled=False,
            value_template='{{ value_json["id"] | int(0) }}',
        )
        self._publish_sensor(
            mqtt_topics.DRIVETRAIN_AUXILIARY_BATTERY_VOLTAGE,
            "Auxiliary battery voltage",
            device_class="voltage",
            state_class="measurement",
            unit_of_measurement="V",
            icon="mdi:car-battery",
        )
        self._publish_sensor(
            mqtt_topics.DRIVETRAIN_RANGE,
            "Range",
            device_class="distance",
            unit_of_measurement="km",
        )
        self._publish_sensor(
            mqtt_topics.DRIVETRAIN_FOSSIL_FUEL_RANGE,
            "Fossil fuel range",
            enabled=self.__vin_info.has_fossil_fuel,
            device_class="distance",
            unit_of_measurement="km",
        )
        self._publish_sensor(
            mqtt_topics.DRIVETRAIN_FOSSIL_FUEL_PERCENTAGE,
            "Fossil fuel percentage",
            enabled=self.__vin_info.has_fossil_fuel,
            state_class="measurement",
            unit_of_measurement="%",
            icon="mdi:fuel",
        )
        self._publish_sensor(
            mqtt_topics.DRIVETRAIN_CURRENT,
            "Current",
            device_class="current",
            state_class="measurement",
            unit_of_measurement="A",
        )
        self._publish_sensor(
            mqtt_topics.DRIVETRAIN_VOLTAGE,
            "Voltage",
            device_class="voltage",
            state_class="measurement",
            unit_of_measurement="V",
        )
        self._publish_sensor(
            mqtt_topics.DRIVETRAIN_POWER,
            "Power",
            device_class="power",
            state_class="measurement",
            unit_of_measurement="kW",
        )

        self.__publish_obc_sensors()
        self.__publish_ccu_sensors()
        self.__publish_location_sensors()
        self.__publish_tyres_sensors()
        # Binary sensors
        self._publish_binary_sensor(
            mqtt_topics.DRIVETRAIN_CHARGER_CONNECTED,
            "Charger connected",
            device_class="plug",
            icon="mdi:power-plug-battery",
        )
        self._publish_binary_sensor(
            mqtt_topics.DRIVETRAIN_HV_BATTERY_ACTIVE,
            "HV Battery Active",
            device_class="power",
            icon="mdi:battery-check",
        )
        self._publish_binary_sensor(
            mqtt_topics.DRIVETRAIN_CHARGING,
            "Battery Charging",
            device_class="battery_charging",
            icon="mdi:battery-charging",
        )
        self._publish_sensor(
            mqtt_topics.DRIVETRAIN_CHARGING_STOP_REASON,
            "Battery charging stop reason",
            icon="mdi:battery-charging",
            enabled=False,
        )
        self._publish_binary_sensor(
            mqtt_topics.DRIVETRAIN_BATTERY_HEATING,
            "Battery heating",
            icon="mdi:heat-wave",
        )
        self._publish_sensor(
            mqtt_topics.DRIVETRAIN_BATTERY_HEATING_STOP_REASON,
            "Battery heating stop reason",
            icon="mdi:heat-wave",
            enabled=False,
        )
        self._publish_binary_sensor(
            mqtt_topics.DRIVETRAIN_RUNNING,
            "Vehicle Running",
            device_class="running",
            icon="mdi:car-side",
        )
        self.__publish_lights_sensors()

        LOG.debug("Completed publishing Home Assistant discovery messages")

    def __publish_location_sensors(self) -> None:
        self.__publish_vehicle_tracker()
        self._publish_sensor(
            mqtt_topics.LOCATION_HEADING,
            "Heading",
            icon="mdi:compass",
            unit_of_measurement="°",
        )
        self._publish_sensor(
            mqtt_topics.LOCATION_SPEED,
            "Vehicle speed",
            device_class="speed",
            unit_of_measurement="km/h",
        )
        self._publish_switch(
            mqtt_topics.LOCATION_FIND_MY_CAR,
            "Find my car",
            icon="mdi:car-search",
            payload_on="activate",
            payload_off="stop",
        )

    def __publish_windows_sensors(self) -> None:
        self._publish_switch(mqtt_topics.WINDOWS_DRIVER, "Window driver")
        self._publish_switch(mqtt_topics.WINDOWS_PASSENGER, "Window passenger")
        self._publish_switch(mqtt_topics.WINDOWS_REAR_LEFT, "Window rear left")
        self._publish_switch(mqtt_topics.WINDOWS_REAR_RIGHT, "Window rear right")
        if self.__vin_info.has_sunroof:
            self._publish_switch(mqtt_topics.WINDOWS_SUN_ROOF, "Sun roof")
            self._publish_binary_sensor(mqtt_topics.WINDOWS_SUN_ROOF, "Sun roof")
        else:
            self.__unpublish_ha_discovery_message("switch", "Sun roof")
            self.__unpublish_ha_discovery_message("binary_sensor", "Sun roof")

    def __publish_ccu_sensors(self) -> None:
        self._publish_sensor(
            mqtt_topics.CCU_ONBOARD_PLUG_STATUS,
            "CCU Onboard Plug Status",
            state_class="measurement",
            entity_category="diagnostic",
            enabled=False,
        )
        self._publish_sensor(
            mqtt_topics.CCU_OFFBOARD_PLUG_STATUS,
            "CCU Offboard Plug Status",
            state_class="measurement",
            entity_category="diagnostic",
            enabled=False,
        )

    def __publish_obc_sensors(self) -> None:
        self._publish_sensor(
            mqtt_topics.OBC_CURRENT,
            "OBC Current",
            device_class="current",
            state_class="measurement",
            unit_of_measurement="A",
            entity_category="diagnostic",
            enabled=False,
        )
        self._publish_sensor(
            mqtt_topics.OBC_VOLTAGE,
            "OBC Voltage",
            device_class="voltage",
            state_class="measurement",
            unit_of_measurement="V",
            entity_category="diagnostic",
            enabled=False,
        )
        self._publish_sensor(
            mqtt_topics.OBC_POWER_SINGLE_PHASE,
            "OBC Power Single Phase",
            device_class="power",
            state_class="measurement",
            unit_of_measurement="W",
            entity_category="diagnostic",
            enabled=False,
        )
        self._publish_sensor(
            mqtt_topics.OBC_POWER_THREE_PHASE,
            "OBC Power Three Phase",
            device_class="power",
            state_class="measurement",
            unit_of_measurement="W",
            entity_category="diagnostic",
            enabled=False,
        )

    def __publish_lights_sensors(self) -> None:
        self._publish_binary_sensor(
            mqtt_topics.LIGHTS_MAIN_BEAM,
            "Lights Main Beam",
            device_class="light",
            icon="mdi:car-light-high",
        )
        self._publish_binary_sensor(
            mqtt_topics.LIGHTS_DIPPED_BEAM,
            "Lights Dipped Beam",
            device_class="light",
            icon="mdi:car-light-dimmed",
        )
        self._publish_binary_sensor(
            mqtt_topics.LIGHTS_SIDE,
            "Lights Side",
            device_class="light",
            icon="mdi:car-light-dimmed",
        )

    def __publish_tyres_sensors(self) -> None:
        self._publish_sensor(
            mqtt_topics.TYRES_FRONT_LEFT_PRESSURE,
            "Tyres front left pressure",
            device_class="pressure",
            unit_of_measurement="bar",
            icon="mdi:tire",
        )
        self._publish_sensor(
            mqtt_topics.TYRES_FRONT_RIGHT_PRESSURE,
            "Tyres front right pressure",
            device_class="pressure",
            unit_of_measurement="bar",
            icon="mdi:tire",
        )
        self._publish_sensor(
            mqtt_topics.TYRES_REAR_LEFT_PRESSURE,
            "Tyres rear left pressure",
            device_class="pressure",
            unit_of_measurement="bar",
            icon="mdi:tire",
        )
        self._publish_sensor(
            mqtt_topics.TYRES_REAR_RIGHT_PRESSURE,
            "Tyres rear right pressure",
            device_class="pressure",
            unit_of_measurement="bar",
            icon="mdi:tire",
        )

    def __publish_doors_sensors(self) -> None:
        self._publish_lock(
            mqtt_topics.DOORS_LOCKED, "Doors Lock", icon="mdi:car-door-lock"
        )
        self._publish_lock(
            mqtt_topics.DOORS_BOOT,
            "Boot Lock",
            icon="mdi:car-door-lock",
            state_locked="False",
            state_unlocked="True",
        )
        self._publish_binary_sensor(
            mqtt_topics.DOORS_DRIVER,
            "Door driver",
            device_class="door",
            icon="mdi:car-door",
        )
        self._publish_binary_sensor(
            mqtt_topics.DOORS_PASSENGER,
            "Door passenger",
            device_class="door",
            icon="mdi:car-door",
        )
        self._publish_binary_sensor(
            mqtt_topics.DOORS_REAR_LEFT,
            "Door rear left",
            device_class="door",
            icon="mdi:car-door",
        )
        self._publish_binary_sensor(
            mqtt_topics.DOORS_REAR_RIGHT,
            "Door rear right",
            device_class="door",
            icon="mdi:car-door",
        )
        self._publish_binary_sensor(
            mqtt_topics.DOORS_BONNET, "Bonnet", device_class="door", icon="mdi:car-door"
        )
        self._publish_binary_sensor(
            mqtt_topics.DOORS_BOOT, "Boot", device_class="door", icon="mdi:car-door"
        )

    def __publish_gateway_sensors(self) -> None:
        options = [m.value for m in RefreshMode]
        self._publish_select(
            mqtt_topics.REFRESH_MODE,
            "Gateway refresh mode",
            options,
            entity_category="config",
            enabled=True,
            value_template="{{ value }}",
            command_template="{{ value }}",
            icon="mdi:refresh",
            custom_availability=self.__system_availability_config,
        )
        self._publish_number(
            mqtt_topics.REFRESH_PERIOD_ACTIVE,
            "Gateway active refresh period",
            entity_category="config",
            unit_of_measurement="s",
            icon="mdi:timer",
            min_value=30,
            max_value=60 * 60,
            step=1,
            custom_availability=self.__system_availability_config,
        )
        self._publish_number(
            mqtt_topics.REFRESH_PERIOD_INACTIVE,
            "Gateway inactive refresh period",
            entity_category="config",
            unit_of_measurement="s",
            icon="mdi:timer",
            min_value=1 * 60 * 60,
            max_value=5 * 24 * 60 * 60,
            step=1,
            custom_availability=self.__system_availability_config,
        )
        self._publish_number(
            mqtt_topics.REFRESH_PERIOD_AFTER_SHUTDOWN,
            "Gateway refresh period after car shutdown",
            entity_category="config",
            unit_of_measurement="s",
            icon="mdi:timer",
            min_value=30,
            max_value=12 * 60 * 60,
            step=1,
            custom_availability=self.__system_availability_config,
        )
        self._publish_number(
            mqtt_topics.REFRESH_PERIOD_INACTIVE_GRACE,
            "Gateway grace period after car shutdown",
            entity_category="config",
            unit_of_measurement="s",
            icon="mdi:timer",
            min_value=30,
            max_value=12 * 60 * 60,
            step=1,
            custom_availability=self.__system_availability_config,
        )
        self._publish_sensor(
            mqtt_topics.REFRESH_PERIOD_CHARGING,
            "Gateway charging refresh period",
            entity_category="diagnostic",
            unit_of_measurement="s",
            icon="mdi:timer",
            custom_availability=self.__system_availability_config,
        )
        self._publish_sensor(
            mqtt_topics.REFRESH_PERIOD_ERROR,
            "Gateway error refresh period",
            entity_category="diagnostic",
            unit_of_measurement="s",
            icon="mdi:timer",
            custom_availability=self.__system_availability_config,
        )
        self._publish_sensor(
            mqtt_topics.REFRESH_LAST_ACTIVITY,
            "Last car activity",
            device_class="timestamp",
            entity_category="diagnostic",
            custom_availability=self.__system_availability_config,
        )
        self._publish_sensor(
            mqtt_topics.REFRESH_LAST_CHARGE_STATE,
            "Last charge state",
            device_class="timestamp",
            entity_category="diagnostic",
            custom_availability=self.__system_availability_config,
        )
        self._publish_sensor(
            mqtt_topics.REFRESH_LAST_VEHICLE_STATE,
            "Last vehicle state",
            device_class="timestamp",
            entity_category="diagnostic",
            custom_availability=self.__system_availability_config,
        )
        self._publish_sensor(
            mqtt_topics.REFRESH_LAST_ERROR,
            "Last poll error",
            device_class="timestamp",
            entity_category="diagnostic",
            custom_availability=self.__system_availability_config,
        )

    def __publish_climate_sensors(self) -> None:
        self.__publish_remote_ac()
        self.__publish_heated_seats()
        self.__publish_back_window_heat()
        self._publish_sensor(
            mqtt_topics.CLIMATE_INTERIOR_TEMPERATURE,
            "Interior temperature",
            device_class="temperature",
            state_class="measurement",
            unit_of_measurement="°C",
        )
        self._publish_sensor(
            mqtt_topics.CLIMATE_EXTERIOR_TEMPERATURE,
            "Exterior temperature",
            device_class="temperature",
            state_class="measurement",
            unit_of_measurement="°C",
        )
        # Remove deprecated sensors
        self.__unpublish_ha_discovery_message(
            "sensor", "Front window defroster heating"
        )

    def __publish_back_window_heat(self) -> None:
        self._publish_switch(
            mqtt_topics.CLIMATE_BACK_WINDOW_HEAT,
            "Rear window defroster heating",
            icon="mdi:car-defrost-rear",
            payload_on="on",
            payload_off="off",
        )
        self._publish_sensor(
            mqtt_topics.CLIMATE_BACK_WINDOW_HEAT,
            "Rear window defroster heating",
            icon="mdi:car-defrost-rear",
        )

    def __publish_vehicle_tracker(self) -> None:
        self._publish_ha_discovery_message(
            "device_tracker",
            "Vehicle position",
            {
                "json_attributes_topic": self.__get_vehicle_topic(
                    mqtt_topics.LOCATION_POSITION
                )
            },
        )

    def __publish_remote_ac(self) -> None:
        # This has been converted into 2 switches and a climate entity for ease of operation

        self._publish_sensor(
            mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE,
            "Remote climate state",
            icon="mdi:car-connected",
        )

        self._publish_switch(
            mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE,
            "Front window defroster heating",
            icon="mdi:car-defrost-front",
            value_template='{% if value == "front" %}front{% else %}off{% endif %}',
            payload_on="front",
            payload_off="off",
        )

        self._publish_switch(
            mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE,
            "Vehicle climate fan only",
            icon="mdi:fan",
            value_template='{% if value == "blowingonly" %}blowingonly{% else %}off{% endif %}',
            payload_on="blowingonly",
            payload_off="off",
        )

        self._publish_ha_discovery_message(
            "climate",
            "Vehicle climate",
            {
                "precision": 1.0,
                "temperature_unit": "C",
                "mode_state_topic": self.__get_vehicle_topic(
                    mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE
                ),
                "mode_command_topic": self.__get_vehicle_topic(
                    mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE_SET
                ),
                "mode_state_template": '{% if value == "on" %}auto{% else %}off{% endif %}',
                "mode_command_template": '{% if value == "auto" %}on{% else %}off{% endif %}',
                "modes": ["off", "auto"],
                "current_temperature_topic": self.__get_vehicle_topic(
                    mqtt_topics.CLIMATE_INTERIOR_TEMPERATURE
                ),
                "current_temperature_template": "{{ value }}",
                "temperature_command_topic": self.__get_vehicle_topic(
                    mqtt_topics.CLIMATE_REMOTE_TEMPERATURE_SET
                ),
                "temperature_command_template": "{{ value | int }}",
                "temperature_state_topic": self.__get_vehicle_topic(
                    mqtt_topics.CLIMATE_REMOTE_TEMPERATURE
                ),
                "temperature_state_template": "{{ value | int }}",
                "min_temp": self.__vin_info.min_ac_temperature,
                "max_temp": self.__vin_info.max_ac_temperature,
            },
        )

    def __get_common_attributes(
        self,
        unique_id: str,
        name: str,
        custom_availability: HaCustomAvailabilityConfig | None = None,
    ) -> dict[str, Any]:
        common_attributes = {
            "name": name,
            "device": self.__get_device_node(),
            "unique_id": unique_id,
            "object_id": unique_id,
        }

        if custom_availability is not None:
            common_attributes.update(custom_availability.to_dict())
        else:
            common_attributes.update(self.__standard_availability_config.to_dict())

        return common_attributes

    def __get_device_node(self) -> dict[str, Any]:
        vin = self.vin
        brand_name = decode_as_utf8(self.__vin_info.brand)
        model_name = decode_as_utf8(self.__vin_info.model)
        model_year = decode_as_utf8(self.__vin_info.model_year)
        color_name = decode_as_utf8(self.__vin_info.color)
        series = str(self.__vin_info.series)
        # Create a long model name concatenating model_name, model_year and color_name without multiple spaces
        final_model_name = f"{model_name} {model_year} {color_name}".strip().replace(
            "  ", " "
        )
        return {
            "name": f"{brand_name} {model_name} {vin}",
            "manufacturer": brand_name,
            "model": final_model_name,
            "hw_version": series,
            "identifiers": [vin],
        }

    @property
    def vin(self) -> str:
        return self.__vin_info.vin

    def __get_system_topic(self, topic: str) -> str:
        publisher = self.__vehicle_state.publisher
        if isinstance(publisher, MqttPublisher):
            return publisher.get_topic(topic, no_prefix=False)
        return topic

    @override
    def _get_state_topic(self, raw_topic: str) -> str:
        return self.__get_vehicle_topic(raw_topic)

    def __get_vehicle_topic(self, topic: str) -> str:
        vehicle_topic: str = self.__vehicle_state.get_topic(topic)
        publisher = self.__vehicle_state.publisher
        if isinstance(publisher, MqttPublisher):
            return publisher.get_topic(vehicle_topic, no_prefix=False)
        return vehicle_topic

    @override
    def _get_command_topic(self, raw_topic: str) -> str:
        return self.__get_vehicle_set_topic(raw_topic)

    def __get_vehicle_set_topic(self, topic: str) -> str:
        return self.__get_vehicle_topic(topic) + "/" + mqtt_topics.SET_SUFFIX

    @override
    def _publish_ha_discovery_message(
        self,
        sensor_type: str,
        sensor_name: str,
        payload: dict[str, Any],
        custom_availability: HaCustomAvailabilityConfig | None = None,
    ) -> str:
        vin = self.vin
        unique_id = f"{vin}_{snake_case(sensor_name)}"
        final_payload = (
            self.__get_common_attributes(unique_id, sensor_name, custom_availability)
            | payload
        )
        ha_topic = (
            f"{self.__discovery_prefix}/{sensor_type}/{vin}_mg/{unique_id}/config"
        )
        self.__vehicle_state.publisher.publish_json(
            ha_topic, final_payload, no_prefix=True
        )
        return f"{sensor_type}.{unique_id}"

    # This de-registers an entity from Home Assistant
    def __unpublish_ha_discovery_message(
        self, sensor_type: str, sensor_name: str
    ) -> None:
        vin = self.vin
        unique_id = f"{vin}_{snake_case(sensor_name)}"
        ha_topic = (
            f"{self.__discovery_prefix}/{sensor_type}/{vin}_mg/{unique_id}/config"
        )
        self.__vehicle_state.publisher.publish_str(ha_topic, "", no_prefix=True)

    def __publish_scheduled_charging(self) -> None:
        start_time_id = self._publish_sensor(
            mqtt_topics.DRIVETRAIN_CHARGING_SCHEDULE,
            "Scheduled Charging Start",
            value_template='{{ value_json["startTime"] }}',
            icon="mdi:clock-start",
        )
        end_time_id = self._publish_sensor(
            mqtt_topics.DRIVETRAIN_CHARGING_SCHEDULE,
            "Scheduled Charging End",
            value_template='{{ value_json["endTime"] }}',
            icon="mdi:clock-end",
        )
        scheduled_charging_mode_id = self._publish_sensor(
            mqtt_topics.DRIVETRAIN_CHARGING_SCHEDULE,
            "Scheduled Charging Mode",
            value_template='{{ value_json["mode"] }}',
            icon="mdi:clock-outline",
        )

        change_mode_cmd_template = json.dumps(
            {
                "startTime": f"{{{{ states('{start_time_id}') }}}}",
                "endTime": f"{{{{ states('{end_time_id}') }}}}",
                "mode": "{{ value }}",
            }
        )
        options = [m.name for m in ScheduledChargingMode]
        self._publish_select(
            mqtt_topics.DRIVETRAIN_CHARGING_SCHEDULE,
            "Scheduled Charging Mode",
            options,
            entity_category=None,
            enabled=True,
            value_template='{{ value_json["mode"] }}',
            command_template=change_mode_cmd_template,
            icon="mdi:clock-outline",
            custom_availability=None,
        )

        change_start_cmd_template = json.dumps(
            {
                "startTime": "{{ value }}",
                "endTime": f"{{{{ states('{end_time_id}') }}}}",
                "mode": f"{{{{ states('{scheduled_charging_mode_id}') }}}}",
            }
        )
        self._publish_text(
            mqtt_topics.DRIVETRAIN_CHARGING_SCHEDULE,
            "Scheduled Charging Start",
            icon="mdi:clock-start",
            value_template='{{ value_json["startTime"] }}',
            command_template=change_start_cmd_template,
            min_value=4,
            max_value=5,
            pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$",
        )

        change_end_cmd_template = json.dumps(
            {
                "startTime": f"{{{{ states('{start_time_id}') }}}}",
                "endTime": "{{ value }}",
                "mode": f"{{{{ states('{scheduled_charging_mode_id}') }}}}",
            }
        )
        self._publish_text(
            mqtt_topics.DRIVETRAIN_CHARGING_SCHEDULE,
            "Scheduled Charging End",
            icon="mdi:clock-end",
            value_template='{{ value_json["endTime"] }}',
            command_template=change_end_cmd_template,
            min_value=4,
            max_value=5,
            pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$",
        )

    def __publish_scheduled_battery_heating(self) -> None:
        start_time_id = self._publish_sensor(
            mqtt_topics.DRIVETRAIN_BATTERY_HEATING_SCHEDULE,
            "Scheduled Battery Heating Start",
            value_template='{{ value_json["startTime"] }}',
            icon="mdi:clock-start",
        )
        mode_id = self._publish_binary_sensor(
            mqtt_topics.DRIVETRAIN_BATTERY_HEATING_SCHEDULE,
            "Scheduled Battery Heating",
            value_template='{{ value_json["mode"] }}',
            payload_on="on",
            payload_off="off",
            icon="mdi:clock-outline",
        )
        change_mode_cmd_template = json.dumps(
            {"startTime": f"{{{{ states('{start_time_id}') }}}}", "mode": "{{ value }}"}
        )
        options = ["on", "off"]
        self._publish_select(
            mqtt_topics.DRIVETRAIN_BATTERY_HEATING_SCHEDULE,
            "Scheduled Battery Heating",
            options,
            entity_category=None,
            enabled=True,
            value_template='{{ value_json["mode"] }}',
            command_template=change_mode_cmd_template,
            icon="mdi:clock-outline",
            custom_availability=None,
        )

        change_start_cmd_template = json.dumps(
            {"startTime": "{{ value }}", "mode": f"{{{{ states('{mode_id}') }}}}"}
        )
        self._publish_text(
            mqtt_topics.DRIVETRAIN_BATTERY_HEATING_SCHEDULE,
            "Scheduled Battery Heating Start",
            icon="mdi:clock-start",
            value_template='{{ value_json["startTime"] }}',
            command_template=change_start_cmd_template,
            min_value=4,
            max_value=5,
            pattern="^([01][0-9]|2[0-3]):[0-5][0-9]$",
        )

    def __publish_heated_seats(self) -> None:
        if self.__vin_info.has_level_heated_seats:
            self.__unpublish_heated_seat_switch("Front Left")
            self.__unpublish_heated_seat_switch("Front Right")
            self.__publish_heated_seat_level(
                "Front Left", mqtt_topics.CLIMATE_HEATED_SEATS_FRONT_LEFT_LEVEL
            )
            self.__publish_heated_seat_level(
                "Front Right", mqtt_topics.CLIMATE_HEATED_SEATS_FRONT_RIGHT_LEVEL
            )
        elif self.__vin_info.has_on_off_heated_seats:
            self.__unpublish_heated_seat_level("Front Left")
            self.__unpublish_heated_seat_level("Front Right")
            self.__publish_heated_seat_switch(
                "Front Left", mqtt_topics.CLIMATE_HEATED_SEATS_FRONT_LEFT_LEVEL
            )
            self.__publish_heated_seat_switch(
                "Front Right", mqtt_topics.CLIMATE_HEATED_SEATS_FRONT_RIGHT_LEVEL
            )
        else:
            self.__unpublish_heated_seat_level("Front Left")
            self.__unpublish_heated_seat_level("Front Right")
            self.__unpublish_heated_seat_switch("Front Left")
            self.__unpublish_heated_seat_switch("Front Right")

    def __publish_heated_seat_level(self, seat: str, topic: str) -> None:
        options = ["OFF", "LOW", "MEDIUM", "HIGH"]
        self._publish_select(
            topic,
            f"Heated Seat {seat} Level",
            options,
            entity_category=None,
            enabled=True,
            value_template="{% set v = value | int %}"
            "{% if v == 0 %}OFF"
            "{% elif v == 1 %}LOW"
            "{% elif v == 2 %}MEDIUM"
            "{% else %}HIGH"
            "{% endif %}",
            command_template='{% if value == "OFF" %}0'
            '{% elif value == "LOW" %}1'
            '{% elif value == "MEDIUM" %}2'
            "{% else %}3"
            "{% endif %}",
            icon="mdi:car-seat-heater",
            custom_availability=None,
        )

    def __unpublish_heated_seat_level(self, seat: str) -> None:
        self.__unpublish_ha_discovery_message("select", f"Heated Seat {seat} Level")

    def __publish_heated_seat_switch(self, seat: str, topic: str) -> None:
        self._publish_switch(
            topic,
            f"Heated Seat {seat}",
            icon="mdi:car-seat-heater",
            payload_on="1",
            payload_off="0",
        )

    def __unpublish_heated_seat_switch(self, seat: str) -> None:
        self.__unpublish_ha_discovery_message("switch", f"Heated Seat {seat}")


