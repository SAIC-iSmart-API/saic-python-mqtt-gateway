import threading
import uuid
import paho.mqtt.client as mqtt

from configuration import Configuration
from publisher import Publisher


class MqttClient(Publisher):
    def __init__(self, configuration: Configuration):
        super().__init__(configuration)
        self.publisher_id = uuid.uuid4()
        self.configuration = configuration
        self.topic_root = configuration.mqtt_topic
        self.is_connected = threading.Event()
        self.client = None
        self.host = self.configuration.mqtt_host
        self.port = self.configuration.mqtt_port
        self.transport_protocol = self.configuration.mqtt_transport_protocol
        self.on_refresh_mode_update = None
        self.on_inactive_refresh_interval_update = None
        self.on_active_refresh_interval_update = None
        self.on_doors_lock_state_update = None
        self.on_rear_window_heat_state_update = None
        self.on_lp_charging = None

        mqtt_client = mqtt.Client(str(self.publisher_id), transport=self.transport_protocol, protocol=mqtt.MQTTv31)
        mqtt_client.on_connect = self.__on_connect
        mqtt_client.on_message = self.__on_message
        self.client = mqtt_client

    def connect(self):
        if self.configuration.mqtt_user is not None:
            if self.configuration.mqtt_password is not None:
                self.client.username_pw_set(username=self.configuration.mqtt_user,
                                            password=self.configuration.mqtt_password)
            else:
                self.client.username_pw_set(username=self.configuration.mqtt_user)
        self.client.connect(host=self.host, port=self.port)
        self.client.loop_start()
        # wait until we've connected
        self.is_connected.wait()

    def __on_connect(self, client, userdata, flags, rc) -> None:
        if rc == mqtt.CONNACK_ACCEPTED:
            self.is_connected.set()

            basic_topic = f'{self.configuration.mqtt_topic}/{self.configuration.saic_user}/vehicles/+'
            self.client.subscribe(f'{basic_topic}/refresh/mode/set')
            self.client.subscribe(f'{basic_topic}/refresh/period/active/set')
            self.client.subscribe(f'{basic_topic}/refresh/period/inActive/set')
            self.client.subscribe(f'{basic_topic}/doors/locked/set')
            self.client.subscribe(f'{basic_topic}/climate/rearWindowDefrosterHeating/set')
            for key in self.configuration.open_wb_lp_map.keys():
                self.client.subscribe(f'{self.configuration.open_wb_topic}/lp/{key}/boolChargeStat')
        else:
            SystemExit(f'Unable to connect to MQTT broker. Return code: {rc}')

    def __on_message(self, client, userdata, msg: mqtt.MQTTMessage) -> None:
        if msg.topic.endswith('/refresh/mode/set'):
            vin = self.get_vin_from_topic(msg.topic)
            mode_value = msg.payload.decode().strip().lower()
            if self.on_refresh_mode_update is not None:
                self.mode_by_vin[vin] = mode_value
                self.on_refresh_mode_update(mode_value, vin)
        elif msg.topic.endswith('/refresh/period/active/set'):
            vin = self.get_vin_from_topic(msg.topic)
            if self.on_active_refresh_interval_update is not None:
                refresh_interval = msg.payload.decode().strip()
                self.on_active_refresh_interval_update(int(refresh_interval), vin)
        elif msg.topic.endswith('/refresh/period/inActive/set'):
            vin = self.get_vin_from_topic(msg.topic)
            if self.on_inactive_refresh_interval_update is not None:
                refresh_interval = msg.payload.decode().strip()
                self.on_inactive_refresh_interval_update(int(refresh_interval), vin)
        elif msg.topic.endswith('/doors/locked/set'):
            vin = self.get_vin_from_topic(msg.topic)
            if self.on_doors_lock_state_update is not None:
                lock_value = msg.payload.decode().strip().lower()
                if lock_value == 'true':
                    self.on_doors_lock_state_update(True, vin)
                elif lock_value == 'false':
                    self.on_doors_lock_state_update(False, vin)
                else:
                    topic = msg.topic[len(self.configuration.mqtt_topic) + 1:-4]
                    self.publish_str(f'{topic}/result', f'Invalid value: {lock_value}. Valid values are true or false')
        elif msg.topic.endswith('/climate/rearWindowDefrosterHeating/set'):
            vin = self.get_vin_from_topic(msg.topic)
            rear_windows_heat_state = msg.payload.decode().strip()
            self.on_rear_window_heat_state_update(rear_windows_heat_state, vin)
        elif msg.topic.endswith('/boolChargeStat'):
            index = self.get_index_from_open_wp_topic(msg.topic)
            vin = self.configuration.open_wb_lp_map[index]
            self.on_lp_charging(vin, msg.payload.decode() == '1')

    def publish(self, msg: mqtt.MQTTMessage) -> None:
        self.client.publish(msg.topic, msg.payload, retain=True)

    def get_topic(self, key: str, no_prefix: bool) -> bytes:
        if no_prefix:
            topic = bytes(f'{key}', encoding='utf8')
        else:
            topic = bytes(f'{self.topic_root}/{key}', encoding='utf8')
        return topic

    def publish_json(self, key: str, data: dict, no_prefix: bool = False) -> None:
        msg = mqtt.MQTTMessage(topic=self.get_topic(key, no_prefix))
        msg.payload = bytes(self.dict_to_anonymized_json(data), encoding='utf8')
        self.publish(msg)

    def publish_str(self, key: str, value: str, no_prefix: bool = False) -> None:
        msg = mqtt.MQTTMessage(topic=self.get_topic(key, no_prefix))
        msg.payload = bytes(value, encoding='utf8')
        self.publish(msg)

    def publish_int(self, key: str, value: int, no_prefix: bool = False) -> None:
        msg = mqtt.MQTTMessage(topic=self.get_topic(key, no_prefix))
        msg.payload = value
        self.publish(msg)

    def publish_bool(self, key: str, value: bool, no_prefix: bool = False) -> None:
        msg = mqtt.MQTTMessage(topic=self.get_topic(key, no_prefix))
        msg.payload = value
        self.publish(msg)

    def publish_float(self, key: str, value: float, no_prefix: bool = False) -> None:
        msg = mqtt.MQTTMessage(topic=self.get_topic(key, no_prefix))
        msg.payload = value
        self.publish(msg)

    def get_vin_from_topic(self, topic: str) -> str:
        global_topic_removed = topic[len(self.configuration.mqtt_topic) + 1:]
        elements = global_topic_removed.split('/')
        return elements[2]

    def get_index_from_open_wp_topic(self, topic: str):
        open_wb_topic_removed = topic[len(f'{self.configuration.open_wb_topic}') + 1:]
        elements = open_wb_topic_removed.split('/')
        return elements[1]
