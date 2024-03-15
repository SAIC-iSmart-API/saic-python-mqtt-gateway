import json
import logging
import os
from typing import List

import inflection as inflection
from saic_ismart_client_ng.api.vehicle.schema import VinInfo
from saic_ismart_client_ng.api.vehicle_charging import ChargeCurrentLimitCode, ScheduledChargingMode

import mqtt_topics
from publisher.mqtt_publisher import MqttClient
from vehicle import VehicleState, RefreshMode

LOG = logging.getLogger(__name__)
LOG.setLevel(level=os.getenv('LOG_LEVEL', 'INFO').upper())


class HaCustomAvailabilityEntry:
    def __init__(
            self, *,
            topic: str,
            template: str | None = None,
            payload_available: str = 'online',
            payload_not_available: str = 'offline',
    ):
        self.__topic = topic
        self.__template = template
        self.__payload_available = payload_available
        self.__payload_not_available = payload_not_available

    def to_dict(self):
        result = {
            'topic': self.__topic,
            'payload_available': self.__payload_available,
            'payload_not_available': self.__payload_not_available
        }
        if self.__template:
            result.update({
                'value_template': self.__template
            })
        return result


class HaCustomAvailabilityConfig:
    def __init__(
            self, *,
            rules: List[HaCustomAvailabilityEntry],
            mode: str = 'all',
    ):
        self.__rules = rules
        self.__mode = mode

    def to_dict(self):
        return {
            'availability': [r.to_dict() for r in self.__rules],
            'availability_mode': self.__mode
        }


class HomeAssistantDiscovery:
    def __init__(self, vehicle_state: VehicleState, vin_info: VinInfo):
        self.__vehicle_state = vehicle_state
        self.__vin_info = vin_info
        self.__vehicle_availability = HaCustomAvailabilityEntry(
            topic=self.__get_vehicle_topic(mqtt_topics.AVAILABLE)
        )
        self.__system_availability = HaCustomAvailabilityEntry(
            topic=self.__get_system_topic(mqtt_topics.INTERNAL_LWT)
        )
        self.__system_availability_config = HaCustomAvailabilityConfig(
            rules=[
                self.__system_availability
            ]
        )
        self.__standard_availability_config = HaCustomAvailabilityConfig(
            rules=[
                self.__system_availability,
                self.__vehicle_availability
            ]
        )

    def publish_ha_discovery_messages(self):
        if not self.__vehicle_state.is_complete():
            LOG.debug("Skipping Home Assistant discovery messages as vehicle state is not yet complete")
            return

        LOG.debug("Publishing Home Assistant discovery messages")

        # Gateway Control
        self.__publish_select(mqtt_topics.REFRESH_MODE, 'Gateway refresh mode', [m.value for m in RefreshMode],
                              icon='mdi:refresh', custom_availability=self.__system_availability_config)
        self.__publish_number(mqtt_topics.REFRESH_PERIOD_ACTIVE, 'Gateway active refresh period',
                              unit_of_measurement='s', icon='mdi:timer', min_value=30, max_value=60 * 60, step=1,
                              custom_availability=self.__system_availability_config)
        self.__publish_number(mqtt_topics.REFRESH_PERIOD_INACTIVE, 'Gateway inactive refresh period',
                              unit_of_measurement='s', icon='mdi:timer', min_value=1 * 60 * 60,
                              max_value=5 * 24 * 60 * 60, step=1,
                              custom_availability=self.__system_availability_config)
        self.__publish_number(mqtt_topics.REFRESH_PERIOD_AFTER_SHUTDOWN, 'Gateway refresh period after car shutdown',
                              unit_of_measurement='s', icon='mdi:timer', min_value=30, max_value=12 * 60 * 60, step=1,
                              custom_availability=self.__system_availability_config)
        self.__publish_number(mqtt_topics.REFRESH_PERIOD_INACTIVE_GRACE, 'Gateway grace period after car shutdown',
                              unit_of_measurement='s', icon='mdi:timer', min_value=30, max_value=12 * 60 * 60, step=1,
                              custom_availability=self.__system_availability_config)
        self.__publish_sensor(mqtt_topics.REFRESH_PERIOD_CHARGING, 'Gateway charging refresh period',
                              unit_of_measurement='s', icon='mdi:timer',
                              custom_availability=self.__system_availability_config)
        self.__publish_sensor(mqtt_topics.REFRESH_PERIOD_ERROR, 'Gateway error refresh period',
                              unit_of_measurement='s', icon='mdi:timer',
                              custom_availability=self.__system_availability_config)
        self.__publish_sensor(mqtt_topics.REFRESH_LAST_ACTIVITY, 'Last car activity', device_class='timestamp',
                              custom_availability=self.__system_availability_config)
        self.__publish_sensor(mqtt_topics.REFRESH_LAST_CHARGE_STATE, 'Last charge state', device_class='timestamp',
                              custom_availability=self.__system_availability_config)
        self.__publish_sensor(mqtt_topics.REFRESH_LAST_VEHICLE_STATE, 'Last vehicle state', device_class='timestamp',
                              custom_availability=self.__system_availability_config)
        self.__publish_sensor(mqtt_topics.REFRESH_LAST_ERROR, 'Last poll error', device_class='timestamp',
                              custom_availability=self.__system_availability_config)

        # Complex sensors
        self.__publish_remote_ac()
        self.__publish_heated_seats()
        self.__publish_vehicle_tracker()
        self.__publish_scheduled_charging()
        self.__publish_scheduled_battery_heating()

        # Switches
        self.__publish_switch(mqtt_topics.DRIVETRAIN_CHARGING, 'Charging')
        self.__publish_switch(mqtt_topics.DRIVETRAIN_BATTERY_HEATING, 'Battery heating', icon='mdi:heat-wave')
        self.__publish_switch(mqtt_topics.WINDOWS_DRIVER, 'Window driver')
        self.__publish_switch(mqtt_topics.WINDOWS_PASSENGER, 'Window passenger')
        self.__publish_switch(mqtt_topics.WINDOWS_REAR_LEFT, 'Window rear left')
        self.__publish_switch(mqtt_topics.WINDOWS_REAR_RIGHT, 'Window rear right')

        if self.__vehicle_state.has_sunroof:
            self.__publish_switch(mqtt_topics.WINDOWS_SUN_ROOF, 'Sun roof')
            self.__publish_binary_sensor(mqtt_topics.WINDOWS_SUN_ROOF, 'Sun roof')
        else:
            self.__unpublish_ha_discovery_message('switch', 'Sun roof')
            self.__unpublish_ha_discovery_message('binary_sensor', 'Sun roof')

        self.__publish_switch(mqtt_topics.CLIMATE_BACK_WINDOW_HEAT, 'Rear window defroster heating',
                              icon='mdi:car-defrost-rear', payload_on='on', payload_off='off')

        # Locks
        self.__publish_lock(mqtt_topics.DOORS_LOCKED, 'Doors Lock', icon='mdi:car-door-lock')
        self.__publish_lock(mqtt_topics.DOORS_BOOT, 'Boot Lock', icon='mdi:car-door-lock', state_locked='False',
                            state_unlocked='True')
        self.__publish_lock(mqtt_topics.DRIVETRAIN_CHARGING_CABLE_LOCK, 'Charging Cable Lock', icon='mdi:lock')

        # Target SoC
        self.__publish_number(
            mqtt_topics.DRIVETRAIN_SOC_TARGET,
            'Target SoC',
            device_class='battery',
            unit_of_measurement='%',
            min_value=40,
            max_value=100,
            step=10,
            mode='slider',
            icon='mdi:battery-charging-70',
            enabled=self.__vehicle_state.supports_target_soc,
        )
        self.__publish_select(mqtt_topics.DRIVETRAIN_CHARGECURRENT_LIMIT, 'Charge current limit',
                              [m.limit for m in ChargeCurrentLimitCode if m != ChargeCurrentLimitCode.C_IGNORE],
                              icon='mdi:current-ac')

        # Standard sensors
        self.__publish_sensor(mqtt_topics.DRIVETRAIN_SOC, 'SoC', device_class='battery', state_class='measurement',
                              unit_of_measurement='%')
        self.__publish_sensor(mqtt_topics.DRIVETRAIN_SOC_KWH,
                              'SoC_kWh',
                              device_class='ENERGY_STORAGE',
                              state_class='measurement',
                              icon='mdi:battery-charging-70',
                              unit_of_measurement='kWh')
        self.__publish_sensor(mqtt_topics.DRIVETRAIN_LAST_CHARGE_ENDING_POWER,
                              'Last Charge SoC kWh',
                              device_class='ENERGY_STORAGE',
                              state_class='measurement',
                              icon='mdi:battery-charging-70',
                              unit_of_measurement='kWh'
                              )
        self.__publish_sensor(mqtt_topics.DRIVETRAIN_POWER_USAGE_SINCE_LAST_CHARGE,
                              'Energy Usage Since Last Charge',
                              device_class='ENERGY_STORAGE',
                              state_class='measurement',
                              icon='mdi:battery-charging-70',
                              unit_of_measurement='kWh',
                              enabled=False
                              )
        self.__publish_sensor(mqtt_topics.DRIVETRAIN_POWER_USAGE_OF_DAY,
                              'Energy Usage of the Day',
                              device_class='ENERGY_STORAGE',
                              state_class='measurement',
                              icon='mdi:battery-charging-70',
                              unit_of_measurement='kWh',
                              enabled=False
                              )

        self.__publish_sensor(mqtt_topics.DRIVETRAIN_REMAINING_CHARGING_TIME, 'Remaining charging time',
                              device_class='duration', state_class='measurement', unit_of_measurement='s')
        custom_availability = HaCustomAvailabilityConfig(rules=[
            self.__standard_availability_config,
            self.__vehicle_availability,
            HaCustomAvailabilityEntry(
                topic=self.__get_vehicle_topic(mqtt_topics.DRIVETRAIN_REMAINING_CHARGING_TIME),
                template="{{ 'online' if (value | int) > 0 else 'offline' }}"
            )
        ])
        self.__publish_sensor(mqtt_topics.DRIVETRAIN_REMAINING_CHARGING_TIME, 'Charging finished',
                              device_class='timestamp',
                              value_template='{{ (now() + timedelta(seconds = value | int)).isoformat() }}',
                              custom_availability=custom_availability)
        self.__publish_sensor(mqtt_topics.DRIVETRAIN_MILEAGE, 'Mileage', device_class='distance',
                              state_class='total_increasing', unit_of_measurement='km')
        self.__publish_sensor(mqtt_topics.DRIVETRAIN_MILEAGE_OF_DAY, 'Mileage of the day', device_class='distance',
                              state_class='total_increasing', unit_of_measurement='km',
                              enabled=False)
        self.__publish_sensor(mqtt_topics.DRIVETRAIN_MILEAGE_SINCE_LAST_CHARGE, 'Mileage since last charge',
                              device_class='distance', state_class='total_increasing', unit_of_measurement='km',
                              enabled=False)
        self.__publish_sensor(mqtt_topics.DRIVETRAIN_AUXILIARY_BATTERY_VOLTAGE, 'Auxiliary battery voltage',
                              device_class='voltage', state_class='measurement', unit_of_measurement='V',
                              icon='mdi:car-battery')
        self.__publish_sensor(mqtt_topics.DRIVETRAIN_RANGE, 'Range', device_class='distance', unit_of_measurement='km')
        self.__publish_sensor(mqtt_topics.DRIVETRAIN_CURRENT, 'Current', device_class='current',
                              state_class='measurement', unit_of_measurement='A')
        self.__publish_sensor(mqtt_topics.DRIVETRAIN_VOLTAGE, 'Voltage', device_class='voltage',
                              state_class='measurement', unit_of_measurement='V')
        self.__publish_sensor(mqtt_topics.DRIVETRAIN_POWER, 'Power', device_class='power', state_class='measurement',
                              unit_of_measurement='kW')
        self.__publish_sensor(mqtt_topics.CLIMATE_INTERIOR_TEMPERATURE, 'Interior temperature',
                              device_class='temperature', state_class='measurement', unit_of_measurement='°C')
        self.__publish_sensor(mqtt_topics.CLIMATE_EXTERIOR_TEMPERATURE, 'Exterior temperature',
                              device_class='temperature', state_class='measurement', unit_of_measurement='°C')
        self.__publish_sensor(mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE, 'Remote climate state',
                              icon='mdi:car-connected')
        self.__publish_sensor(mqtt_topics.CLIMATE_BACK_WINDOW_HEAT, 'Rear window defroster heating',
                              icon='mdi:car-defrost-rear')
        self.__publish_sensor(mqtt_topics.LOCATION_HEADING, 'Heading', icon='mdi:compass')
        self.__publish_sensor(mqtt_topics.LOCATION_SPEED, 'Vehicle speed', device_class='speed',
                              unit_of_measurement='km/h')
        self.__publish_sensor(mqtt_topics.TYRES_FRONT_LEFT_PRESSURE, 'Tyres front left pressure',
                              device_class='pressure', unit_of_measurement='bar', icon='mdi:tire')
        self.__publish_sensor(mqtt_topics.TYRES_FRONT_RIGHT_PRESSURE, 'Tyres front right pressure',
                              device_class='pressure', unit_of_measurement='bar', icon='mdi:tire')
        self.__publish_sensor(mqtt_topics.TYRES_REAR_LEFT_PRESSURE, 'Tyres rear left pressure', device_class='pressure',
                              unit_of_measurement='bar', icon='mdi:tire')
        self.__publish_sensor(mqtt_topics.TYRES_REAR_RIGHT_PRESSURE, 'Tyres rear right pressure',
                              device_class='pressure', unit_of_measurement='bar', icon='mdi:tire')
        # Binary sensors
        self.__publish_binary_sensor(mqtt_topics.DRIVETRAIN_CHARGER_CONNECTED, 'Charger connected',
                                     device_class='plug', icon='mdi:power-plug-battery')
        self.__publish_binary_sensor(mqtt_topics.DRIVETRAIN_HV_BATTERY_ACTIVE, 'HV Battery Active',
                                     device_class='power', icon='mdi:battery-check')
        self.__publish_binary_sensor(mqtt_topics.DRIVETRAIN_CHARGING, 'Battery Charging',
                                     device_class='battery_charging', icon='mdi:battery-charging')
        self.__publish_binary_sensor(mqtt_topics.DRIVETRAIN_BATTERY_HEATING, 'Battery heating', icon='mdi:heat-wave')
        self.__publish_binary_sensor(mqtt_topics.DRIVETRAIN_RUNNING, 'Vehicle Running', device_class='running',
                                     icon='mdi:car-side')
        self.__publish_binary_sensor(mqtt_topics.DOORS_DRIVER, 'Door driver', device_class='door', icon='mdi:car-door')
        self.__publish_binary_sensor(mqtt_topics.DOORS_PASSENGER, 'Door passenger', device_class='door',
                                     icon='mdi:car-door')
        self.__publish_binary_sensor(mqtt_topics.DOORS_REAR_LEFT, 'Door rear left', device_class='door',
                                     icon='mdi:car-door')
        self.__publish_binary_sensor(mqtt_topics.DOORS_REAR_RIGHT, 'Door rear right', device_class='door',
                                     icon='mdi:car-door')
        self.__publish_binary_sensor(mqtt_topics.DOORS_BONNET, 'Bonnet', device_class='door', icon='mdi:car-door')
        self.__publish_binary_sensor(mqtt_topics.DOORS_BOOT, 'Boot', device_class='door', icon='mdi:car-door')
        self.__publish_binary_sensor(mqtt_topics.LIGHTS_MAIN_BEAM, 'Lights Main Beam', device_class='light',
                                     icon='mdi:car-light-high')
        self.__publish_binary_sensor(mqtt_topics.LIGHTS_DIPPED_BEAM, 'Lights Dipped Beam', device_class='light',
                                     icon='mdi:car-light-dimmed')

        # Remove deprecated sensors
        self.__unpublish_ha_discovery_message('sensor', 'Front window defroster heating')
        LOG.debug("Completed publishing Home Assistant discovery messages")

    def __publish_vehicle_tracker(self):
        self.__publish_ha_discovery_message('device_tracker', 'Vehicle position', {
            'json_attributes_topic': self.__get_vehicle_topic(mqtt_topics.LOCATION_POSITION)
        })

    def __publish_remote_ac(self):
        # This has been converted into 2 switches and a climate entity for ease of operation

        self.__publish_ha_discovery_message('switch', 'Front window defroster heating', {
            'icon': 'mdi:car-defrost-front',
            'state_topic': self.__get_vehicle_topic(mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE),
            'command_topic': self.__get_vehicle_topic(mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE) + '/set',
            'value_template': '{% if value == "front" %}front{% else %}off{% endif %}',
            'state_on': 'front',
            'state_off': 'off',
            'payload_on': 'front',
            'payload_off': 'off',
        })

        self.__publish_ha_discovery_message('switch', 'Vehicle climate fan only', {
            'icon': 'mdi:fan',
            'state_topic': self.__get_vehicle_topic(mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE),
            'command_topic': self.__get_vehicle_topic(mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE) + '/set',
            'value_template': '{% if value == "blowingonly" %}blowingonly{% else %}off{% endif %}',
            'state_on': 'blowingonly',
            'state_off': 'off',
            'payload_on': 'blowingonly',
            'payload_off': 'off',
        })

        self.__publish_ha_discovery_message('climate', 'Vehicle climate', {
            'precision': 1.0,
            'temperature_unit': 'C',
            'mode_state_topic': self.__get_vehicle_topic(mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE),
            'mode_command_topic': self.__get_vehicle_topic(mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE) + '/set',
            'mode_state_template': '{% if value == "on" %}auto{% else %}off{% endif %}',
            'mode_command_template': '{% if value == "auto" %}on{% else %}off{% endif %}',
            'modes': ['off', 'auto'],
            'current_temperature_topic': self.__get_vehicle_topic(mqtt_topics.CLIMATE_INTERIOR_TEMPERATURE),
            'current_temperature_template': '{{ value }}',
            'temperature_command_topic': self.__get_vehicle_topic(mqtt_topics.CLIMATE_REMOTE_TEMPERATURE) + '/set',
            'temperature_command_template': '{{ value | int }}',
            'temperature_state_topic': self.__get_vehicle_topic(mqtt_topics.CLIMATE_REMOTE_TEMPERATURE),
            'temperature_state_template': '{{ value | int }}',
            'min_temp': self.__vehicle_state.get_min_ac_temperature(),
            'max_temp': self.__vehicle_state.get_max_ac_temperature(),
        })

    def __publish_switch(
            self,
            topic: str,
            name: str,
            *,
            enabled=True,
            icon: str | None = None,
            value_template: str = '{{ value }}',
            payload_on='True',
            payload_off='False',
            custom_availability: HaCustomAvailabilityConfig | None = None
    ) -> str:
        payload = {
            'state_topic': self.__get_vehicle_topic(topic),
            'command_topic': self.__get_vehicle_topic(topic) + '/set',
            'value_template': value_template,
            'payload_on': payload_on,
            'payload_off': payload_off,
            'optimistic': False,
            'qos': 0,
            'enabled_by_default': enabled,
        }
        if icon is not None:
            payload['icon'] = icon
        return self.__publish_ha_discovery_message('switch', name, payload, custom_availability)

    def __publish_lock(
            self,
            topic: str,
            name: str,
            enabled=True,
            icon: str | None = None,
            payload_lock: str = 'True',
            payload_unlock: str = 'False',
            state_locked: str = 'True',
            state_unlocked: str = 'False',
            custom_availability: HaCustomAvailabilityConfig | None = None
    ) -> str:
        payload = {
            'state_topic': self.__get_vehicle_topic(topic),
            'command_topic': self.__get_vehicle_topic(topic) + '/set',
            'payload_lock': payload_lock,
            'payload_unlock': payload_unlock,
            'state_locked': state_locked,
            'state_unlocked': state_unlocked,
            'optimistic': False,
            'qos': 0,
            'enabled_by_default': enabled,
        }
        if icon is not None:
            payload['icon'] = icon
        return self.__publish_ha_discovery_message('lock', name, payload, custom_availability)

    def __publish_sensor(
            self,
            topic: str,
            name: str,
            enabled=True,
            device_class: str | None = None,
            state_class: str | None = None,
            unit_of_measurement: str | None = None,
            icon: str | None = None,
            value_template: str = '{{ value }}',
            custom_availability: HaCustomAvailabilityConfig | None = None
    ) -> str:
        payload = {
            'state_topic': self.__get_vehicle_topic(topic),
            'value_template': value_template,
            'enabled_by_default': enabled,
        }
        if device_class is not None:
            payload['device_class'] = device_class
        if state_class is not None:
            payload['state_class'] = state_class
        if unit_of_measurement is not None:
            payload['unit_of_measurement'] = unit_of_measurement
        if icon is not None:
            payload['icon'] = icon

        return self.__publish_ha_discovery_message('sensor', name, payload, custom_availability)

    def __publish_number(
            self,
            topic: str,
            name: str,
            enabled=True,
            device_class: str | None = None,
            state_class: str | None = None,
            unit_of_measurement: str | None = None,
            icon: str | None = None,
            value_template: str = '{{ value }}',
            retain: bool = False,
            mode: str = 'auto',
            min_value: float = 1.0,
            max_value: float = 100.0,
            step: float = 1.0,
            custom_availability: HaCustomAvailabilityConfig | None = None
    ) -> str:
        payload = {
            'state_topic': self.__get_vehicle_topic(topic),
            'command_topic': self.__get_vehicle_topic(topic) + '/set',
            'value_template': value_template,
            'retain': str(retain).lower(),
            'mode': mode,
            'min': min_value,
            'max': max_value,
            'step': step,
            'enabled_by_default': enabled,
        }
        if device_class is not None:
            payload['device_class'] = device_class
        if state_class is not None:
            payload['state_class'] = state_class
        if unit_of_measurement is not None:
            payload['unit_of_measurement'] = unit_of_measurement
        if icon is not None:
            payload['icon'] = icon

        return self.__publish_ha_discovery_message('number', name, payload, custom_availability)

    def __publish_text(
            self,
            topic: str,
            name: str,
            enabled=True,
            icon: str | None = None,
            value_template: str = '{{ value }}',
            command_template: str = '{{ value }}',
            retain: bool = False,
            min_value: int | None = None,
            max_value: int | None = None,
            pattern: str | None = None,
            custom_availability: HaCustomAvailabilityConfig | None = None
    ) -> str:
        payload = {
            'state_topic': self.__get_vehicle_topic(topic),
            'command_topic': self.__get_vehicle_topic(topic) + '/set',
            'value_template': value_template,
            'command_template': command_template,
            'retain': str(retain).lower(),
            'enabled_by_default': enabled,
        }
        if min_value is not None:
            payload['min'] = min_value
        if max_value is not None:
            payload['max'] = max_value
        if pattern is not None:
            payload['pattern'] = pattern
        if icon is not None:
            payload['icon'] = icon

        return self.__publish_ha_discovery_message('text', name, payload, custom_availability)

    def __publish_binary_sensor(
            self,
            topic: str,
            name: str,
            enabled=True,
            device_class: str | None = None,
            value_template: str = '{{ value }}',
            payload_on: str = 'True',
            payload_off: str = 'False',
            icon: str | None = None,
            custom_availability: HaCustomAvailabilityConfig | None = None
    ) -> str:
        payload = {
            'state_topic': self.__get_vehicle_topic(topic),
            'value_template': value_template,
            'payload_on': payload_on,
            'payload_off': payload_off,
            'enabled_by_default': enabled,
        }
        if device_class is not None:
            payload['device_class'] = device_class
        if icon is not None:
            payload['icon'] = icon

        return self.__publish_ha_discovery_message('binary_sensor', name, payload, custom_availability)

    def __publish_select(
            self,
            topic: str,
            name: str,
            options: list[str],
            enabled=True,
            value_template: str = '{{ value }}',
            command_template: str = '{{ value }}',
            icon: str | None = None,
            custom_availability: HaCustomAvailabilityConfig | None = None
    ) -> str:
        payload = {
            'state_topic': self.__get_vehicle_topic(topic),
            'command_topic': self.__get_vehicle_topic(topic) + '/set',
            'value_template': value_template,
            'command_template': command_template,
            'options': options,
            'enabled_by_default': enabled,
        }
        if icon is not None:
            payload['icon'] = icon

        return self.__publish_ha_discovery_message('select', name, payload, custom_availability)

    def __get_common_attributes(
            self,
            unique_id: str, name: str,
            custom_availability: HaCustomAvailabilityConfig | None = None
    ):
        common_attributes = {
            'name': name,
            'device': self.__get_device_node(),
            'unique_id': unique_id,
            'object_id': unique_id
        }

        if custom_availability is not None:
            common_attributes.update(custom_availability.to_dict())
        else:
            common_attributes.update(self.__standard_availability_config.to_dict())

        return common_attributes

    def __get_device_node(self):
        vin = self.__get_vin()
        brand_name = decode_as_utf8(self.__vin_info.brandName)
        model_name = decode_as_utf8(self.__vin_info.modelName)
        model_year = decode_as_utf8(self.__vin_info.modelYear)
        color_name = decode_as_utf8(self.__vin_info.colorName)
        series = str(self.__vin_info.series)
        # Create a long model name concatenating model_name, model_year and color_name without multiple spaces
        final_model_name = ' '.join([model_name, model_year, color_name]).strip().replace('  ', ' ')
        return {
            'name': f'{brand_name} {model_name} {vin}',
            'manufacturer': brand_name,
            'model': final_model_name,
            'hw_version': series,
            'identifiers': [vin],
        }

    def __get_vin(self):
        vin = self.__vehicle_state.vin
        return vin

    def __get_system_topic(self, topic: str) -> str:
        publisher = self.__vehicle_state.publisher
        if isinstance(publisher, MqttClient):
            return publisher.get_topic(topic, no_prefix=False)
        return topic

    def __get_vehicle_topic(self, topic: str) -> str:
        vehicle_topic = self.__vehicle_state.get_topic(topic)
        publisher = self.__vehicle_state.publisher
        if isinstance(publisher, MqttClient):
            return publisher.get_topic(vehicle_topic, no_prefix=False)
        return vehicle_topic

    def __publish_ha_discovery_message(
            self,
            sensor_type: str,
            sensor_name: str,
            payload: dict,
            custom_availability: dict[str, str] | None = None
    ) -> str:
        vin = self.__get_vin()
        unique_id = f'{vin}_{snake_case(sensor_name)}'
        final_payload = self.__get_common_attributes(unique_id, sensor_name, custom_availability) | payload
        discovery_prefix = self.__vehicle_state.publisher.configuration.ha_discovery_prefix
        ha_topic = f'{discovery_prefix}/{sensor_type}/{vin}_mg/{unique_id}/config'
        self.__vehicle_state.publisher.publish_json(ha_topic, final_payload, no_prefix=True)
        return f"{sensor_type}.{unique_id}"

    # This de-registers an entity from Home Assistant
    def __unpublish_ha_discovery_message(self, sensor_type: str, sensor_name: str) -> None:
        vin = self.__get_vin()
        unique_id = f'{vin}_{snake_case(sensor_name)}'
        discovery_prefix = self.__vehicle_state.publisher.configuration.ha_discovery_prefix
        ha_topic = f'{discovery_prefix}/{sensor_type}/{vin}_mg/{unique_id}/config'
        self.__vehicle_state.publisher.publish_str(ha_topic, '', no_prefix=True)

    def __publish_scheduled_charging(self):
        start_time_id = self.__publish_sensor(
            mqtt_topics.DRIVETRAIN_CHARGING_SCHEDULE,
            'Scheduled Charging Start',
            value_template='{{ value_json["startTime"] }}', icon='mdi:clock-start'
        )
        end_time_id = self.__publish_sensor(
            mqtt_topics.DRIVETRAIN_CHARGING_SCHEDULE,
            'Scheduled Charging End',
            value_template='{{ value_json["endTime"] }}', icon='mdi:clock-end'
        )
        scheduled_charging_mode_id = self.__publish_sensor(
            mqtt_topics.DRIVETRAIN_CHARGING_SCHEDULE,
            'Scheduled Charging Mode',
            value_template='{{ value_json["mode"] }}', icon='mdi:clock-outline',
        )

        change_mode_cmd_template = json.dumps({
            "startTime": f"{{{{ states('{start_time_id}') }}}}",
            "endTime": f"{{{{ states('{end_time_id}') }}}}",
            "mode": "{{ value }}"
        })
        self.__publish_select(
            mqtt_topics.DRIVETRAIN_CHARGING_SCHEDULE,
            'Scheduled Charging Mode',
            options=[m.name for m in ScheduledChargingMode],
            value_template='{{ value_json["mode"] }}',
            command_template=change_mode_cmd_template,
            icon='mdi:clock-outline',
        )

        change_start_cmd_template = json.dumps({
            "startTime": "{{ value }}",
            "endTime": f"{{{{ states('{end_time_id}') }}}}",
            "mode": f"{{{{ states('{scheduled_charging_mode_id}') }}}}"
        })
        self.__publish_text(
            mqtt_topics.DRIVETRAIN_CHARGING_SCHEDULE,
            'Scheduled Charging Start',
            value_template='{{ value_json["startTime"] }}',
            command_template=change_start_cmd_template,
            min_value=4, max_value=5, pattern='^([01][0-9]|2[0-3]):[0-5][0-9]$',
            icon='mdi:clock-start'
        )

        change_end_cmd_template = json.dumps({
            "startTime": f"{{{{ states('{start_time_id}') }}}}",
            "endTime": "{{ value }}",
            "mode": f"{{{{ states('{scheduled_charging_mode_id}') }}}}"
        })
        self.__publish_text(
            mqtt_topics.DRIVETRAIN_CHARGING_SCHEDULE,
            'Scheduled Charging End',
            value_template='{{ value_json["endTime"] }}',
            command_template=change_end_cmd_template,
            min_value=4, max_value=5, pattern='^([01][0-9]|2[0-3]):[0-5][0-9]$',
            icon='mdi:clock-end'
        )

    def __publish_scheduled_battery_heating(self):
        start_time_id = self.__publish_sensor(
            mqtt_topics.DRIVETRAIN_BATTERY_HEATING_SCHEDULE,
            'Scheduled Battery Heating Start',
            value_template='{{ value_json["startTime"] }}', icon='mdi:clock-start'
        )
        mode_id = self.__publish_binary_sensor(
            mqtt_topics.DRIVETRAIN_BATTERY_HEATING_SCHEDULE,
            'Scheduled Battery Heating',
            value_template='{{ value_json["mode"] }}', icon='mdi:clock-outline',
            payload_on='on', payload_off='off'
        )
        change_mode_cmd_template = json.dumps({
            "startTime": f"{{{{ states('{start_time_id}') }}}}",
            "mode": "{{ value }}"
        })
        self.__publish_select(
            mqtt_topics.DRIVETRAIN_BATTERY_HEATING_SCHEDULE,
            'Scheduled Battery Heating',
            options=["on", "off"],
            value_template='{{ value_json["mode"] }}',
            command_template=change_mode_cmd_template,
            icon='mdi:clock-outline',
        )

        change_start_cmd_template = json.dumps({
            "startTime": "{{ value }}",
            "mode": f"{{{{ states('{mode_id}') }}}}"
        })
        self.__publish_text(
            mqtt_topics.DRIVETRAIN_BATTERY_HEATING_SCHEDULE,
            'Scheduled Battery Heating Start',
            value_template='{{ value_json["startTime"] }}',
            command_template=change_start_cmd_template,
            min_value=4, max_value=5, pattern='^([01][0-9]|2[0-3]):[0-5][0-9]$',
            icon='mdi:clock-start'
        )

    def __publish_heated_seats(self):
        if self.__vehicle_state.has_level_heated_seats:
            self.__unpublish_heated_seat_switch('Front Left')
            self.__unpublish_heated_seat_switch('Front Right')
            self.__publish_heated_seat_level('Front Left', mqtt_topics.CLIMATE_HEATED_SEATS_FRONT_LEFT_LEVEL)
            self.__publish_heated_seat_level('Front Right', mqtt_topics.CLIMATE_HEATED_SEATS_FRONT_RIGHT_LEVEL)
        elif self.__vehicle_state.has_on_off_heated_seats:
            self.__unpublish_heated_seat_level('Front Left')
            self.__unpublish_heated_seat_level('Front Right')
            self.__publish_heated_seat_switch('Front Left', mqtt_topics.CLIMATE_HEATED_SEATS_FRONT_LEFT_LEVEL)
            self.__publish_heated_seat_switch('Front Right', mqtt_topics.CLIMATE_HEATED_SEATS_FRONT_RIGHT_LEVEL)
        else:
            self.__unpublish_heated_seat_level('Front Left')
            self.__unpublish_heated_seat_level('Front Right')
            self.__unpublish_heated_seat_switch('Front Left')
            self.__unpublish_heated_seat_switch('Front Right')

    def __publish_heated_seat_level(self, seat: str, topic: str):
        self.__publish_select(
            topic,
            f'Heated Seat {seat} Level',
            options=['OFF', 'LOW', 'MEDIUM', 'HIGH'],
            value_template='{% set v = value | int %}'
                           '{% if v == 0 %}OFF'
                           '{% elif v == 1 %}LOW'
                           '{% elif v == 2 %}MEDIUM'
                           '{% else %}HIGH'
                           '{% endif %}',
            command_template='{% if value == "OFF" %}0'
                             '{% elif value == "LOW" %}1'
                             '{% elif value == "MEDIUM" %}2'
                             '{% else %}3'
                             '{% endif %}',
            icon='mdi:car-seat-heater',
        )

    def __unpublish_heated_seat_level(self, seat: str):
        self.__unpublish_ha_discovery_message('select', f'Heated Seat {seat} Level')

    def __publish_heated_seat_switch(self, seat: str, topic: str):
        self.__publish_switch(
            topic,
            f'Heated Seat {seat}',
            payload_off='0',
            payload_on='1',
            icon='mdi:car-seat-heater',
        )

    def __unpublish_heated_seat_switch(self, seat: str):
        self.__unpublish_ha_discovery_message('switch', f'Heated Seat {seat}')


def snake_case(s):
    return inflection.underscore(s.lower()).replace(' ', '_')


def decode_as_utf8(byte_string, default=''):
    if byte_string is None:
        return default
    elif isinstance(byte_string, str):
        return byte_string
    elif isinstance(byte_string, bytes) or isinstance(byte_string, bytearray):
        try:
            return str(byte_string, encoding='utf8', errors='ignore')
        except Exception:
            LOG.exception(f'Failed to decode {byte_string} as utf8')
            return default
    else:
        try:
            return str(byte_string)
        except Exception:
            LOG.exception(f'Failed to decode {byte_string}')
            return default
