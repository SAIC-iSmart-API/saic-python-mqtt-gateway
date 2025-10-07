from __future__ import annotations

import asyncio
import logging
import ssl
from typing import TYPE_CHECKING, Any, override

import aiomqtt

import mqtt_topics
from publisher.core import Publisher

if TYPE_CHECKING:
    from configuration import Configuration
    from integrations.openwb.charging_station import ChargingStation

LOG = logging.getLogger(__name__)


class MqttPublisher(Publisher):
    def __init__(
        self,
        configuration: Configuration,
    ) -> None:
        super().__init__(configuration)
        self.publisher_id = configuration.mqtt_client_id
        self.host = self.configuration.mqtt_host
        self.port = self.configuration.mqtt_port
        self.transport_protocol = self.configuration.mqtt_transport_protocol
        self.vin_by_charge_state_topic: dict[str, str] = {}
        self.last_charge_state_by_vin: dict[str, str] = {}
        self.vin_by_charger_connected_topic: dict[str, str] = {}
        self.first_connection = True
        self.client: None | aiomqtt.Client = None
        self.__running: asyncio.Task[None] | None = None
        self.__connected = asyncio.Event()

    async def __run_loop(self) -> None:
        if not self.host:
            LOG.info("MQTT host is not configured")
            return
        ssl_context: ssl.SSLContext | None = None
        if self.transport_protocol.with_tls:
            ssl_context = ssl.create_default_context()
            if self.configuration.tls_server_cert_path:
                LOG.debug(
                    f"Using custom CA file {self.configuration.tls_server_cert_path}"
                )
                ssl_context.load_verify_locations(
                    cafile=self.configuration.tls_server_cert_path
                )
                if not self.configuration.tls_server_cert_check_hostname:
                    LOG.warning(
                        f"Skipping hostname check for TLS connection to {self.host}"
                    )

        client = aiomqtt.Client(
            hostname=self.host,
            port=self.port,
            identifier=str(self.publisher_id) + "a",
            transport=self.transport_protocol.transport_mechanism,
            username=self.configuration.mqtt_user or None,
            password=self.configuration.mqtt_password or None,
            clean_session=True,
            tls_context=ssl_context,
            tls_insecure=bool(
                ssl_context and not self.configuration.tls_server_cert_check_hostname
            ),
            will=aiomqtt.Will(
                topic=self.get_topic(mqtt_topics.INTERNAL_LWT, False),
                payload="offline",
                retain=True,
            ),
        )
        client.pending_calls_threshold = 150
        self.client = client
        reconnect_interval = 5
        while True:
            try:
                async with client:
                    self.__connected.set()
                    await self.__on_connect()
                    async for message in client.messages:
                        await self._on_message(
                            client,
                            str(message.topic),
                            message.payload,
                            message.qos,
                            message.properties,
                        )
            except aiomqtt.MqttError as e:
                LOG.error(
                    f"Connection to MQTT broker lost; Reconnecting in {reconnect_interval} seconds ...: {e}"
                )
                await asyncio.sleep(reconnect_interval)
            except asyncio.exceptions.CancelledError:
                LOG.debug("MQTT publisher loop cancelled")
                raise
            finally:
                self.__connected.clear()
                self.client = None
                LOG.info("MQTT client disconnected")

    @override
    async def connect(self) -> None:
        if self.__running and not self.__running.done():
            LOG.warning("MQTT client is already running")
            return
        self.__running = asyncio.create_task(self.__run_loop())
        await self.__connected.wait()

    async def __on_connect(self) -> None:
        LOG.info("Connected to MQTT broker")
        if not self.first_connection:
            await self.__enable_commands()
        self.first_connection = False
        self.keepalive()

    @override
    def enable_commands(self) -> None:
        loop = asyncio.get_running_loop()
        asyncio.run_coroutine_threadsafe(self.__enable_commands(), loop)

    async def __enable_commands(self) -> None:
        if not self.__connected.is_set() or not self.client:
            LOG.error("MQTT client is not connected")
            return
        try:
            LOG.info("Subscribing to MQTT command topics")
            mqtt_account_prefix = self.get_mqtt_account_prefix()
            await self.client.subscribe(
                f"{mqtt_account_prefix}/{mqtt_topics.VEHICLES}/+/+/+/{mqtt_topics.SET_SUFFIX}"
            )
            await self.client.subscribe(
                f"{mqtt_account_prefix}/{mqtt_topics.VEHICLES}/+/+/+/+/{mqtt_topics.SET_SUFFIX}"
            )
            await self.client.subscribe(
                f"{mqtt_account_prefix}/{mqtt_topics.VEHICLES}/+/{mqtt_topics.REFRESH_MODE}/{mqtt_topics.SET_SUFFIX}"
            )
            await self.client.subscribe(
                f"{mqtt_account_prefix}/{mqtt_topics.VEHICLES}/+/{mqtt_topics.REFRESH_PERIOD}/+/{mqtt_topics.SET_SUFFIX}"
            )
            for (
                charging_station
            ) in self.configuration.charging_stations_by_vin.values():
                LOG.debug(
                    f"Subscribing to MQTT topic {charging_station.charge_state_topic}"
                )
                self.vin_by_charge_state_topic[charging_station.charge_state_topic] = (
                    charging_station.vin
                )
                await self.client.subscribe(charging_station.charge_state_topic)
                if charging_station.connected_topic:
                    LOG.debug(
                        f"Subscribing to MQTT topic {charging_station.connected_topic}"
                    )
                    self.vin_by_charger_connected_topic[
                        charging_station.connected_topic
                    ] = charging_station.vin
                    await self.client.subscribe(charging_station.connected_topic)
            if self.configuration.ha_discovery_enabled:
                # enable dynamic discovery pushing in case ha reconnects
                await self.client.subscribe(self.configuration.ha_lwt_topic)
        except aiomqtt.MqttError as e:
            LOG.error("Failed to subscribe to MQTT command topics: {e}")
            raise e

    async def _on_message(
        self, _client: Any, topic: str, payload: Any, _qos: Any, _properties: Any
    ) -> None:
        try:
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8")
            else:
                payload = str(payload)
            await self.__on_message_real(topic=topic, payload=payload)
        except Exception as e:
            LOG.exception(f"Error while processing MQTT message: {e}")

    async def __on_message_real(self, *, topic: str, payload: str) -> None:
        if topic in self.vin_by_charge_state_topic:
            LOG.debug(f"Received message over topic {topic} with payload {payload}")
            vin = self.vin_by_charge_state_topic[topic]
            charging_station = self.configuration.charging_stations_by_vin[vin]
            if self.should_force_refresh(payload, charging_station):
                LOG.info(
                    f"Vehicle with vin {vin} is charging. Setting refresh mode to force"
                )
                if self.command_listener is not None:
                    await self.command_listener.on_charging_detected(vin)
        elif topic in self.vin_by_charger_connected_topic:
            LOG.debug(f"Received message over topic {topic} with payload {payload}")
            vin = self.vin_by_charger_connected_topic[topic]
            charging_station = self.configuration.charging_stations_by_vin[vin]
            if payload == charging_station.connected_value:
                LOG.debug(
                    f"Vehicle with vin {vin} is connected to its charging station"
                )
            else:
                LOG.debug(
                    f"Vehicle with vin {vin} is disconnected from its charging station"
                )
        elif topic == self.configuration.ha_lwt_topic:
            if self.command_listener is not None:
                await self.command_listener.on_mqtt_global_command_received(
                    topic=topic, payload=payload
                )
        else:
            vin = self.get_vin_from_topic(topic)
            if self.command_listener is not None:
                await self.command_listener.on_mqtt_command_received(
                    vin=vin, topic=topic, payload=payload
                )

    def __publish(self, topic: str, payload: Any) -> None:
        if not (self.client and self.is_connected()):
            LOG.error("MQTT client is not connected")
            return
        loop = asyncio.get_running_loop()
        asyncio.run_coroutine_threadsafe(
            self.__async_publish(topic, payload, retain=True), loop
        )
        LOG.debug(f"Publishing to MQTT topic {topic} with payload {payload}")

    async def __async_publish(self, topic: str, payload: Any, retain: bool) -> None:
        if not (self.client and self.is_connected()):
            LOG.error("MQTT client is not connected")
            return
        try:
            await self.client.publish(topic, payload, retain)
        except aiomqtt.MqttError as e:
            LOG.error(
                f"Failed to publish to MQTT topic {topic} with payload {payload}: {e}"
            )

    @override
    def is_connected(self) -> bool:
        return self.__connected.is_set()

    @override
    def publish_json(
        self, key: str, data: dict[str, Any], no_prefix: bool = False
    ) -> None:
        payload = self.dict_to_anonymized_json(data)
        self.__publish(topic=self.get_topic(key, no_prefix), payload=payload)

    @override
    def publish_str(self, key: str, value: str, no_prefix: bool = False) -> None:
        self.__publish(topic=self.get_topic(key, no_prefix), payload=value)

    @override
    def publish_int(self, key: str, value: int, no_prefix: bool = False) -> None:
        self.__publish(topic=self.get_topic(key, no_prefix), payload=value)

    @override
    def publish_bool(self, key: str, value: bool, no_prefix: bool = False) -> None:
        self.__publish(topic=self.get_topic(key, no_prefix), payload=value)

    @override
    def publish_float(self, key: str, value: float, no_prefix: bool = False) -> None:
        self.__publish(topic=self.get_topic(key, no_prefix), payload=value)

    @override
    def clear_topic(self, key: str, no_prefix: bool = False) -> None:
        self.__publish(topic=self.get_topic(key, no_prefix), payload=None)

    def get_vin_from_topic(self, topic: str) -> str:
        global_topic_removed = topic[len(self.configuration.mqtt_topic) + 1 :]
        elements = global_topic_removed.split("/")
        return elements[2]

    def should_force_refresh(
        self, current_charging_value: str, charging_station: ChargingStation
    ) -> bool:
        vin = charging_station.vin
        last_charging_value: str | None = None
        if vin in self.last_charge_state_by_vin:
            last_charging_value = self.last_charge_state_by_vin[vin]
        self.last_charge_state_by_vin[vin] = current_charging_value

        if last_charging_value:
            if last_charging_value == current_charging_value:
                LOG.debug(
                    "Last charging value equals current charging value. No refresh needed."
                )
                return False
            LOG.info(
                f"Charging value has changed from {last_charging_value} to {current_charging_value}."
            )
            return True
        return True
