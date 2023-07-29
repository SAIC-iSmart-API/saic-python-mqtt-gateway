import json

import inflection as inflection
from saic_ismart_client.common_model import ScheduledChargingMode
from saic_ismart_client.ota_v1_1.data_model import VinInfo
from saic_ismart_client.common_model import ChargeCurrentLimitCode

import mqtt_topics
from mqtt_publisher import MqttClient
from vehicle import VehicleState, RefreshMode


class HomeAssistantDiscovery:
    def __init__(self, vehicle_state: VehicleState, vin_info: VinInfo):
        self.__vehicle_state = vehicle_state
        self.__vin_info = vin_info

    def publish_ha_discovery_messages(self):
        if not self.__vehicle_state.is_complete():
            return
        # Gateway Control
        self.__publish_select(mqtt_topics.REFRESH_MODE, 'Gateway refresh mode', [m.value for m in RefreshMode],
                              icon='mdi:refresh')
        self.__publish_select(mqtt_topics.DRIVETRAIN_CHARGECURRENT_LIMIT, 'Charge current limit',
                              [m.get_limit() for m in ChargeCurrentLimitCode if m != ChargeCurrentLimitCode.C_IGNORE],
                              icon='mdi:current-ac')
        self.__publish_number(mqtt_topics.REFRESH_PERIOD_ACTIVE, 'Gateway active refresh period',
                              unit_of_measurement='s', icon='mdi:timer', min=30, max=60 * 60, step=1)
        self.__publish_number(mqtt_topics.REFRESH_PERIOD_INACTIVE, 'Gateway inactive refresh period',
                              unit_of_measurement='s', icon='mdi:timer', min=1 * 60 * 60,
                              max=5 * 24 * 60 * 60, step=1)
        self.__publish_number(mqtt_topics.REFRESH_PERIOD_AFTER_SHUTDOWN, 'Gateway refresh period after car shutdown',
                              unit_of_measurement='s', icon='mdi:timer', min=30, max=12 * 60 * 60, step=1)
        self.__publish_number(mqtt_topics.REFRESH_PERIOD_INACTIVE_GRACE, 'Gateway grace period after car shutdown',
                              unit_of_measurement='s', icon='mdi:timer', min=30, max=12 * 60 * 60, step=1)

        self.__publish_sensor(mqtt_topics.REFRESH_PERIOD_CHARGING, 'Gateway charging refresh period',
                              unit_of_measurement='s', icon='mdi:timer')
        self.__publish_sensor(mqtt_topics.REFRESH_LAST_ACTIVITY, 'Last car activity', device_class='timestamp', )
        self.__publish_sensor(mqtt_topics.REFRESH_LAST_CHARGE_STATE, 'Last charge state', device_class='timestamp', )
        self.__publish_sensor(mqtt_topics.REFRESH_LAST_VEHICLE_STATE, 'Last vehicle state', device_class='timestamp', )

        # Complex sensors
        self.__publish_remote_ac()
        self.__publish_vehicle_tracker()
        self.__publish_scheduled_charging()

        # Switches
        self.__publish_switch(mqtt_topics.DRIVETRAIN_CHARGING, 'Charging')
        self.__publish_switch(mqtt_topics.WINDOWS_DRIVER, 'Window driver')
        self.__publish_switch(mqtt_topics.WINDOWS_PASSENGER, 'Window passenger')
        self.__publish_switch(mqtt_topics.WINDOWS_REAR_LEFT, 'Window rear left')
        self.__publish_switch(mqtt_topics.WINDOWS_REAR_RIGHT, 'Window rear right')
        self.__publish_switch(mqtt_topics.WINDOWS_SUN_ROOF, 'Sun roof', enabled=self.__vehicle_state.has_sunroof())
        self.__publish_switch(mqtt_topics.CLIMATE_BACK_WINDOW_HEAT, 'Rear window defroster heating',
                              icon='mdi:car-defrost-rear', payload_on='on', payload_off='off')
        # Locks
        self.__publish_lock(mqtt_topics.DOORS_LOCKED, 'Doors Lock', icon='mdi:car-door-lock')
        self.__publish_lock(mqtt_topics.DOORS_BOOT, 'Boot Lock', icon='mdi:car-door-lock', state_locked='False',
                            state_unlocked='True')
        # Target SoC
        self.__publish_number(
            mqtt_topics.DRIVETRAIN_SOC_TARGET,
            'Target SoC',
            device_class='battery',
            unit_of_measurement='%',
            min=40,
            max=100,
            step=10,
            mode='slider',
            icon='mdi:battery-charging-70',
        )

        # Standard sensors
        self.__publish_sensor(mqtt_topics.DRIVETRAIN_SOC, 'SoC', device_class='battery', state_class='measurement',
                              unit_of_measurement='%')
        self.__publish_sensor(mqtt_topics.DRIVETRAIN_REMAINING_CHARGING_TIME, 'Remaining charging time',
                              device_class='duration', state_class='measurement', unit_of_measurement='s')
        self.__publish_sensor(mqtt_topics.DRIVETRAIN_MILEAGE, 'Mileage', device_class='distance',
                              state_class='total_increasing', unit_of_measurement='km')
        self.__publish_sensor(mqtt_topics.DRIVETRAIN_MILEAGE_OF_DAY, 'Mileage of the day', device_class='distance',
                              state_class='total_increasing', unit_of_measurement='km')
        self.__publish_sensor(mqtt_topics.DRIVETRAIN_MILEAGE_SINCE_LAST_CHARGE, 'Mileage since last charge',
                              device_class='distance', state_class='total_increasing', unit_of_measurement='km')
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
        self.__publish_sensor(mqtt_topics.CLIMATE_FRONT_WINDOW_HEAT, 'Front window defroster heating',
                              icon='mdi:car-defrost-front')
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
        self.__publish_binary_sensor(mqtt_topics.DRIVETRAIN_CHARGER_CONNECTED, 'Charger connected', device_class='plug',
                                     icon='mdi:power-plug-battery')
        self.__publish_binary_sensor(mqtt_topics.DRIVETRAIN_CHARGING, 'Battery Charging',
                                     device_class='battery_charging', icon='mdi:battery-charging')
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

    def __publish_vehicle_tracker(self):
        self.__publish_ha_discovery_message('device_tracker', 'Vehicle position', {
            'json_attributes_topic': self.__get_vehicle_topic(mqtt_topics.LOCATION_POSITION)
        })

    def __publish_remote_ac(self):
        self.__publish_ha_discovery_message('climate', 'Vehicle climate', {
            'precision': 1.0,
            'temperature_unit': 'C',
            'mode_state_topic': self.__get_vehicle_topic(mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE),
            'mode_command_topic': self.__get_vehicle_topic(mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE) + '/set',
            'mode_state_template': '{% if value == "off" %}off{% else %}auto{% endif %}',
            'mode_command_template': '{% if value == "off" %}off{% else %}on{% endif %}',
            'modes': ['off', 'auto'],
            'preset_modes': ['off', 'on', 'blowingOnly', 'front'],
            'preset_mode_command_topic': self.__get_vehicle_topic(mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE) + '/set',
            'preset_mode_state_topic': self.__get_vehicle_topic(mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE),
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
            enabled=True,
            icon: str | None = None,
            payload_on='True',
            payload_off='False',
    ) -> str:
        payload = {
            'state_topic': self.__get_vehicle_topic(topic),
            'command_topic': self.__get_vehicle_topic(topic) + '/set',
            'payload_on': payload_on,
            'payload_off': payload_off,
            'optimistic': False,
            'qos': 0,
            'enabled_by_default': enabled,
        }
        if icon is not None:
            payload['icon'] = icon
        return self.__publish_ha_discovery_message('switch', name, payload)

    def __publish_lock(
            self,
            topic: str,
            name: str,
            icon: str | None = None,
            payload_lock: str = 'True',
            payload_unlock: str = 'False',
            state_locked: str = 'True',
            state_unlocked: str = 'False',
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
        }
        if icon is not None:
            payload['icon'] = icon
        return self.__publish_ha_discovery_message('lock', name, payload)

    def __publish_sensor(
            self,
            topic: str,
            name: str,
            device_class: str | None = None,
            state_class: str | None = None,
            unit_of_measurement: str | None = None,
            icon: str | None = None,
            value_template: str = '{{ value }}',
    ) -> str:
        payload = {
            'state_topic': self.__get_vehicle_topic(topic),
            'value_template': value_template,
        }
        if device_class is not None:
            payload['device_class'] = device_class
        if state_class is not None:
            payload['state_class'] = state_class
        if unit_of_measurement is not None:
            payload['unit_of_measurement'] = unit_of_measurement
        if icon is not None:
            payload['icon'] = icon

        return self.__publish_ha_discovery_message('sensor', name, payload)

    def __publish_number(
            self,
            topic: str,
            name: str,
            device_class: str | None = None,
            state_class: str | None = None,
            unit_of_measurement: str | None = None,
            icon: str | None = None,
            value_template: str = '{{ value }}',
            retain: bool = False,
            mode: str = 'auto',
            min: float = 1.0,
            max: float = 100.0,
            step: float = 1.0,
    ) -> str:
        payload = {
            'state_topic': self.__get_vehicle_topic(topic),
            'command_topic': self.__get_vehicle_topic(topic) + '/set',
            'value_template': value_template,
            'retain': str(retain).lower(),
            'mode': mode,
            'min': min,
            'max': max,
            'step': step,
        }
        if device_class is not None:
            payload['device_class'] = device_class
        if state_class is not None:
            payload['state_class'] = state_class
        if unit_of_measurement is not None:
            payload['unit_of_measurement'] = unit_of_measurement
        if icon is not None:
            payload['icon'] = icon

        return self.__publish_ha_discovery_message('number', name, payload)

    def __publish_text(
            self,
            topic: str,
            name: str,
            icon: str | None = None,
            value_template: str = '{{ value }}',
            command_template: str = '{{ value }}',
            retain: bool = False,
            min: int | None = None,
            max: int | None = None,
            pattern: str | None = None,
    ) -> str:
        payload = {
            'state_topic': self.__get_vehicle_topic(topic),
            'command_topic': self.__get_vehicle_topic(topic) + '/set',
            'value_template': value_template,
            'command_template': command_template,
            'retain': str(retain).lower(),
        }
        if min is not None:
            payload['min'] = min
        if max is not None:
            payload['max'] = max
        if pattern is not None:
            payload['pattern'] = pattern
        if icon is not None:
            payload['icon'] = icon

        return self.__publish_ha_discovery_message('text', name, payload)

    def __publish_binary_sensor(
            self,
            topic: str,
            name: str,
            device_class: str | None = None,
            value_template: str = '{{ value }}',
            payload_on: str = 'True',
            payload_off: str = 'False',
            icon: str | None = None,
    ) -> str:
        payload = {
            'state_topic': self.__get_vehicle_topic(topic),
            'value_template': value_template,
            'payload_on': payload_on,
            'payload_off': payload_off,
        }
        if device_class is not None:
            payload['device_class'] = device_class
        if icon is not None:
            payload['icon'] = icon

        return self.__publish_ha_discovery_message('binary_sensor', name, payload)

    def __publish_select(
            self,
            topic: str,
            name: str,
            options: list[str],
            value_template: str = '{{ value }}',
            command_template: str = '{{ value }}',
            icon: str | None = None,
    ) -> str:
        payload = {
            'state_topic': self.__get_vehicle_topic(topic),
            'command_topic': self.__get_vehicle_topic(topic) + '/set',
            'value_template': value_template,
            'command_template': command_template,
            'options': options,
        }
        if icon is not None:
            payload['icon'] = icon

        return self.__publish_ha_discovery_message('select', name, payload)

    def __get_common_attributes(self, id, name):
        return {
            'name': name,
            'device': self.__get_device_node(),
            'unique_id': id,
            'object_id': id,
            'availability_topic': self.__get_system_topic(mqtt_topics.INTERNAL_LWT),
            'payload_available': 'online',
            'payload_not_available': 'offline',
        }

    def __get_device_node(self):
        vin = self.__get_vin()
        brand_name = str(self.__vin_info.brand_name, encoding='utf8')
        model_name = str(self.__vin_info.model_name, encoding='utf8')
        model_year = str(self.__vin_info.model_year)
        color_name = str(self.__vin_info.color_name, encoding='utf8')
        series = str(self.__vin_info.series)
        return {
            'name': f'{brand_name} {model_name} {vin}',
            'manufacturer': brand_name,
            'model': f'{model_name} {model_year} {color_name}',
            'hw_version': series,
            'identifiers': [vin],
        }

    def __get_vin(self):
        vin = self.__vehicle_state.vin
        return vin

    def __get_system_topic(self, topic: str) -> str:
        publisher = self.__vehicle_state.publisher
        if isinstance(publisher, MqttClient):
            return str(publisher.get_topic(topic, no_prefix=False), encoding='utf8')
        return topic

    def __get_vehicle_topic(self, topic: str) -> str:
        vehicle_topic = self.__vehicle_state.get_topic(topic)
        publisher = self.__vehicle_state.publisher
        if isinstance(publisher, MqttClient):
            return str(publisher.get_topic(vehicle_topic, no_prefix=False), encoding='utf8')
        return vehicle_topic

    def __publish_ha_discovery_message(self, sensor_type: str, sensor_name: str, payload: dict) -> str:
        vin = self.__get_vin()
        unique_id = f'{vin}_{snake_case(sensor_name)}'
        final_payload = self.__get_common_attributes(unique_id, sensor_name) | payload
        discovery_prefix = self.__vehicle_state.publisher.configuration.ha_discovery_prefix
        ha_topic = f'{discovery_prefix}/{sensor_type}/{vin}_mg/{unique_id}/config'
        self.__vehicle_state.publisher.publish_json(ha_topic, final_payload, no_prefix=True)
        return f"{sensor_type}.{unique_id}"

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
            min=4, max=5, pattern='^([01][0-9]|2[0-3]):[0-5][0-9]$',
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
            min=4, max=5, pattern='^([01][0-9]|2[0-3]):[0-5][0-9]$',
            icon='mdi:clock-end'
        )


def snake_case(s):
    return inflection.underscore(s.lower()).replace(' ', '_')
