import inflection as inflection
from saic_ismart_client.ota_v1_1.data_model import VinInfo

import mqtt_topics
from mqtt_publisher import MqttClient
from vehicle import VehicleState


class HomeAssistantDiscovery:
    def __init__(self, vehicle_state: VehicleState, vin_info: VinInfo):
        self.__vehicle_state = vehicle_state
        self.__vin_info = vin_info

    def publish_ha_discovery_messages(self):
        if not self.__vehicle_state.is_complete():
            return
        # AC
        self.__publish_remote_ac()
        # Switches
        self.__publish_switch(mqtt_topics.DRIVETRAIN_CHARGING, 'Charging')
        self.__publish_switch(mqtt_topics.WINDOWS_DRIVER, 'Window driver')
        self.__publish_switch(mqtt_topics.WINDOWS_PASSENGER, 'Window passenger')
        self.__publish_switch(mqtt_topics.WINDOWS_REAR_LEFT, 'Window rear left')
        self.__publish_switch(mqtt_topics.WINDOWS_REAR_RIGHT, 'Window rear right')
        self.__publish_switch(mqtt_topics.WINDOWS_SUN_ROOF, 'Sun roof', enabled=self.__vehicle_state.has_sunroof())
        # Locks
        self.__publish_lock(mqtt_topics.DOORS_LOCKED, 'Doors Lock', icon='mdi:car-door-lock')
        # Number
        self.__publish_target_soc()

        # Vehicle Tracker
        self.__publish_vehicle_tracker()
        # Standard sensors
        self.__publish_sensor(mqtt_topics.DRIVETRAIN_SOC, 'SoC', device_class='battery', state_class='measurement',
                              unit_of_measurement='%')
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
            'mode_command_topic': self.__get_vehicle_topic(mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE) + '/set',
            'mode_state_topic': self.__get_vehicle_topic(mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE),
            'modes': ['off', 'on', 'front'],
            'current_temperature_topic': self.__get_vehicle_topic(mqtt_topics.CLIMATE_INTERIOR_TEMPERATURE),
            'current_temperature_template': '{{ value }}',
            'temperature_command_topic': self.__get_vehicle_topic(mqtt_topics.CLIMATE) + '/remoteTemperature/set',
            'temperature_state_template': '{{ value | int }}',
        })

    def __publish_switch(
            self,
            topic: str,
            name: str,
            enabled=True,
    ):
        self.__publish_ha_discovery_message('switch', name, {
            'state_topic': self.__get_vehicle_topic(topic),
            'command_topic': self.__get_vehicle_topic(topic) + '/set',
            'payload_on': 'True',
            'payload_off': 'False',
            'optimistic': False,
            'qos': 0,
            'enabled_by_default': enabled,
        })

    def __publish_lock(
            self,
            topic: str,
            name: str,
            icon: str | None = None,
    ):
        payload = {
            'state_topic': self.__get_vehicle_topic(topic),
            'command_topic': self.__get_vehicle_topic(topic) + '/set',
            'payload_lock': 'True',
            'payload_unlock': 'False',
            'state_locked': 'True',
            'state_unlocked': 'False',
            'optimistic': False,
            'qos': 0,
        }
        if icon is not None:
            payload['icon'] = icon
        self.__publish_ha_discovery_message('lock', name, payload)

    def __publish_sensor(
            self,
            topic: str,
            name: str,
            device_class: str | None = None,
            state_class: str | None = None,
            unit_of_measurement: str | None = None,
            icon: str | None = None,
            value_template: str = '{{ value }}',
    ):
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

        self.__publish_ha_discovery_message('sensor', name, payload)

    def __publish_binary_sensor(
            self,
            topic: str,
            name: str,
            device_class: str | None = None,
            value_template: str = '{{ value }}',
            icon: str | None = None,
    ):
        payload = {
            'state_topic': self.__get_vehicle_topic(topic),
            'value_template': value_template,
            'payload_on': 'True',
            'payload_off': 'False',
        }
        if device_class is not None:
            payload['device_class'] = device_class
        if icon is not None:
            payload['icon'] = icon

        self.__publish_ha_discovery_message('binary_sensor', name, payload)

    def __publish_target_soc(self):
        self.__publish_ha_discovery_message('number', 'Target SoC', {
            'state_topic': self.__get_vehicle_topic(mqtt_topics.DRIVETRAIN_SOC_TARGET),
            'command_topic': self.__get_vehicle_topic(mqtt_topics.DRIVETRAIN_SOC_TARGET) + '/set',
            'value_template': '{{ value }}',
            'device_class': 'battery',
            'unit_of_measurement': '%',
            'min': 40,
            'max': 100,
            'step': 10,
            'mode': 'slider',
            'icon': 'mdi:battery-charging-70',
        })

    def __get_common_attributes(self, id, name):
        return {
            'name': name,
            'device': self.__get_device_node(),
            'unique_id': id,
            'object_id': id,
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

    def __get_vehicle_topic(self, topic: str) -> str:
        vehicle_topic = self.__vehicle_state.get_topic(topic)
        publisher = self.__vehicle_state.publisher
        if isinstance(publisher, MqttClient):
            return str(publisher.get_topic(vehicle_topic, no_prefix=False), encoding='utf8')
        return vehicle_topic

    def __publish_ha_discovery_message(self, sensor_type: str, sensor_name: str, payload: dict):
        vin = self.__get_vin()
        unique_id = f'{vin}_{snake_case(sensor_name)}'
        final_payload = self.__get_common_attributes(unique_id, sensor_name) | payload
        discovery_prefix = self.__vehicle_state.publisher.configuration.ha_discovery_prefix
        ha_topic = f'{discovery_prefix}/{sensor_type}/{vin}_mg/{unique_id}/config'
        self.__vehicle_state.publisher.publish_json(ha_topic, final_payload, no_prefix=True)


def snake_case(s):
    return inflection.underscore(s.lower()).replace(' ', '_')
