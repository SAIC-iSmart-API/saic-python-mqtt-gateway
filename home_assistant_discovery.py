import inflection as inflection

import mqtt_topics
from mqtt_publisher import MqttClient
from saic_ismart_client.common_model import TargetBatteryCode
from vehicle import VehicleState


class HomeAssistantDiscovery():
    def __init__(self, vehicle_state: VehicleState):
        self.vehicle_state = vehicle_state
        self.already_ran = False

    def publish_ha_discovery_messages(self):
        if (not self.vehicle_state.is_complete()) or self.already_ran:
            return
        # AC
        self.__publish_remote_ac()
        # Switches
        self.__publish_switch(mqtt_topics.DRIVETRAIN_CHARGING, 'Charging')
        self.__publish_switch(mqtt_topics.WINDOWS_DRIVER, 'Window driver')
        self.__publish_switch(mqtt_topics.WINDOWS_PASSENGER, 'Window passenger')
        self.__publish_switch(mqtt_topics.WINDOWS_REAR_LEFT, 'Window rearLeft')
        self.__publish_switch(mqtt_topics.WINDOWS_REAR_RIGHT, 'Window rearRight')
        self.__publish_switch(mqtt_topics.WINDOWS_SUN_ROOF, 'Sun roof')
        # Locks
        self.__publish_lock(mqtt_topics.DOORS_LOCKED, 'Doors Lock')
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
                              device_class='voltage', state_class='measurement', unit_of_measurement='V')
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
        self.__publish_sensor(mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE, 'Remote climate state')
        self.__publish_sensor(mqtt_topics.CLIMATE_BACK_WINDOW_HEAT, 'Rear window defroster heating')
        self.__publish_sensor(mqtt_topics.CLIMATE_FRONT_WINDOW_HEAT, 'Front window defroster heating')
        self.__publish_sensor(mqtt_topics.LOCATION_HEADING, 'Heading')
        self.__publish_sensor(mqtt_topics.LOCATION_SPEED, 'Vehicle speed', device_class='speed',
                              unit_of_measurement='km/h')
        self.__publish_sensor(mqtt_topics.TYRES_FRONT_LEFT_PRESSURE, 'Tyres front left pressure',
                              device_class='pressure', unit_of_measurement='bar')
        self.__publish_sensor(mqtt_topics.TYRES_FRONT_RIGHT_PRESSURE, 'Tyres front right pressure',
                              device_class='pressure', unit_of_measurement='bar')
        self.__publish_sensor(mqtt_topics.TYRES_REAR_LEFT_PRESSURE, 'Tyres rear left pressure', device_class='pressure',
                              unit_of_measurement='bar')
        self.__publish_sensor(mqtt_topics.TYRES_REAR_RIGHT_PRESSURE, 'Tyres rear right pressure',
                              device_class='pressure', unit_of_measurement='bar')
        # Binary sensors
        self.__publish_binary_sensor(mqtt_topics.DRIVETRAIN_CHARGER_CONNECTED, 'Charger connected', device_class='plug')
        self.__publish_binary_sensor(mqtt_topics.DRIVETRAIN_CHARGING, 'Battery Charging',
                                     device_class='battery_charging')
        self.__publish_binary_sensor(mqtt_topics.DRIVETRAIN_RUNNING, 'Vehicle Running', device_class='running')
        self.__publish_binary_sensor(mqtt_topics.DOORS_DRIVER, 'Door driver', device_class='door')
        self.__publish_binary_sensor(mqtt_topics.DOORS_PASSENGER, 'Door passenger', device_class='door')
        self.__publish_binary_sensor(mqtt_topics.DOORS_REAR_LEFT, 'Door rear left', device_class='door')
        self.__publish_binary_sensor(mqtt_topics.DOORS_REAR_RIGHT, 'Door rear right', device_class='door')
        self.__publish_binary_sensor(mqtt_topics.DOORS_BONNET, 'Bonnet', device_class='door')
        self.__publish_binary_sensor(mqtt_topics.DOORS_BOOT, 'Boot', device_class='door')
        self.__publish_binary_sensor(mqtt_topics.LIGHTS_MAIN_BEAM, 'Lights Main Beam', device_class='light')
        self.__publish_binary_sensor(mqtt_topics.LIGHTS_DIPPED_BEAM, 'Lights Dipped Beam', device_class='light')

        self.already_ran = True

    def __publish_vehicle_tracker(self):
        vin = self.__get_vin()
        self.__publish_ha_discovery_message(f'device_tracker/{vin}_mg/{vin}_gps_position/config', {
            'name': 'Vehicle position',
            'device': self.__get_device_node(),
            'unique_id': f'{vin}_gps_position',
            'json_attributes_topic': self.__get_vehicle_topic(mqtt_topics.LOCATION_POSITION)
        })

    def __publish_remote_ac(self):
        vin = self.__get_vin()
        unique_id = f'{vin}_climate'
        self.__publish_ha_discovery_message(f'climate/{vin}_mg/{unique_id}/config', {
            'name': 'Vehicle climate',
            'device': self.__get_device_node(),
            'unique_id': unique_id,
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
            switch_name: str,
    ):
        vin = self.__get_vin()
        unique_id = f'{vin}_{snake_case(switch_name)}'
        self.__publish_ha_discovery_message(f'switch/{vin}_mg/{unique_id}/config', {
            'name': switch_name,
            'device': self.__get_device_node(),
            'unique_id': unique_id,
            'state_topic': self.__get_vehicle_topic(topic),
            'command_topic': self.__get_vehicle_topic(topic) + '/set',
            'payload_on': 'true',
            'payload_off': 'false',
            'optimistic': False,
            'qos': 0,
        })

    def __publish_lock(
            self,
            topic: str,
            name: str,
    ):
        vin = self.__get_vin()
        unique_id = f'{vin}_{snake_case(name)}'
        self.__publish_ha_discovery_message(f'lock/{vin}_mg/{unique_id}/config', {
            'name': name,
            'device': self.__get_device_node(),
            'unique_id': unique_id,
            'state_topic': self.__get_vehicle_topic(topic),
            'command_topic': self.__get_vehicle_topic(topic) + '/set',
            'payload_lock': 'true',
            'payload_unlock': 'false',
            'optimistic': False,
            'qos': 0,
        })

    def __publish_sensor(
            self,
            topic: str,
            name: str,
            device_class: str = None,
            state_class: str = None,
            unit_of_measurement: str = None,
            value_template: str = '{{ value }}',
    ):
        vin = self.__get_vin()
        unique_id = f'{vin}_{snake_case(name)}'
        payload = {
            'name': name,
            'device': self.__get_device_node(),
            'unique_id': unique_id,
            'state_topic': self.__get_vehicle_topic(topic),
            'value_template': value_template,
        }
        if device_class is not None:
            payload['device_class'] = device_class
        if state_class is not None:
            payload['state_class'] = state_class
        if unit_of_measurement is not None:
            payload['unit_of_measurement'] = unit_of_measurement

        self.__publish_ha_discovery_message(f'sensor/{vin}_mg/{unique_id}/config', payload)

    def __publish_binary_sensor(
            self,
            topic: str,
            name: str,
            device_class: str = None,
            value_template: str = '{{ value }}',
    ):
        vin = self.__get_vin()
        unique_id = f'{vin}_{snake_case(name)}'
        payload = {
            'name': name,
            'device': self.__get_device_node(),
            'unique_id': unique_id,
            'state_topic': self.__get_vehicle_topic(topic),
            'value_template': value_template,
            'payload_on': 'True',
            'payload_off': 'False',
        }
        if device_class is not None:
            payload['device_class'] = device_class

        self.__publish_ha_discovery_message(f'binary_sensor/{vin}_mg/{unique_id}/config', payload)

    def __publish_target_soc(self):
        vin = self.__get_vin()
        unique_id = f'{vin}_target_soc'
        self.__publish_ha_discovery_message(f'number/{vin}_mg/{unique_id}/config', {
            'name': 'Target SoC',
            'device': self.__get_device_node(),
            'unique_id': unique_id,
            'state_topic': self.__get_vehicle_topic(mqtt_topics.DRIVETRAIN_SOC_TARGET),
            'command_topic': self.__get_vehicle_topic(mqtt_topics.DRIVETRAIN_SOC_TARGET) + '/set',
            'value_template': '{{ value }}',
            'device_class': 'battery',
            'unit_of_measurement': '%',
            'min': TargetBatteryCode.P_40.get_percentage(),
            'max': TargetBatteryCode.P_100.get_percentage(),
            'step': 10,
            'mode': 'slider',
        })

    def __get_vin(self):
        vin = self.vehicle_state.vin
        return vin

    def __get_device_node(self):
        vin = self.__get_vin()
        device_node = {
            'name': f'MG {vin}',
            'manufacturer': 'SAIC Motor',
            'identifiers': [vin],
        }
        return device_node

    def __get_vehicle_topic(self, topic: str) -> str:
        vehicle_topic = self.vehicle_state.get_topic(topic)
        publisher = self.vehicle_state.publisher
        if isinstance(publisher, MqttClient):
            return str(publisher.get_topic(vehicle_topic, no_prefix=False), encoding='utf8')
        return vehicle_topic

    def __publish_ha_discovery_message(self, topic: str, payload: dict):
        discovery_prefix = self.vehicle_state.publisher.configuration.ha_discovery_prefix
        self.vehicle_state.publisher.publish_json(f'{discovery_prefix}/{topic}', payload, no_prefix=True)


def snake_case(s):
    return inflection.underscore(s).replace(' ', '_')
