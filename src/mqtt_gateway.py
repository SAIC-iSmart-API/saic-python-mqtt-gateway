from __future__ import annotations

import asyncio
from asyncio import Task
import logging
from random import uniform
from typing import TYPE_CHECKING, Any, override

import apscheduler.schedulers.asyncio
from saic_ismart_client_ng import SaicApi
from saic_ismart_client_ng.api.vehicle.alarm import AlarmType
from saic_ismart_client_ng.model import SaicApiConfiguration

from exceptions import MqttGatewayException
from handlers.message import MessageHandler
from handlers.relogin import ReloginHandler
from handlers.vehicle import VehicleHandler, VehicleHandlerLocator
import mqtt_topics
from publisher.core import MqttCommandListener, Publisher
from publisher.log_publisher import ConsolePublisher
from publisher.mqtt_publisher import MqttPublisher
from saic_api_listener import MqttGatewaySaicApiListener
from vehicle import VehicleState
from vehicle_info import VehicleInfo

if TYPE_CHECKING:
    from saic_ismart_client_ng.api.vehicle import VinInfo

    from configuration import Configuration
    from integrations.openwb.charging_station import ChargingStation

MSG_CMD_SUCCESSFUL = "Success"

LOG = logging.getLogger(__name__)


class MqttGateway(MqttCommandListener, VehicleHandlerLocator):
    def __init__(self, config: Configuration) -> None:
        self.configuration = config
        self.__vehicle_handlers: dict[str, VehicleHandler] = {}
        self.publisher = self.__select_publisher()
        self.publisher.command_listener = self
        if config.publish_raw_api_data:
            listener = MqttGatewaySaicApiListener(self.publisher)
        else:
            listener = None

        if not self.configuration.saic_user or not self.configuration.saic_password:
            raise MqttGatewayException("Please configure saic username and password")

        self.saic_api = SaicApi(
            configuration=SaicApiConfiguration(
                username=self.configuration.saic_user,
                password=self.configuration.saic_password,
                username_is_email=config.username_is_email,
                phone_country_code=config.saic_phone_country_code,
                base_uri=self.configuration.saic_rest_uri,
                region=self.configuration.saic_region,
                tenant_id=self.configuration.saic_tenant_id,
                read_timeout=self.configuration.saic_read_timeout,
            ),
            listener=listener,
        )
        self.__scheduler = apscheduler.schedulers.asyncio.AsyncIOScheduler()
        self.__relogin_handler = ReloginHandler(
            relogin_relay=self.configuration.saic_relogin_delay,
            api=self.saic_api,
            scheduler=self.__scheduler,
        )

    def __select_publisher(self) -> Publisher:
        if self.configuration.is_mqtt_enabled:
            return MqttPublisher(self.configuration)
        LOG.warning("MQTT support disabled")
        return ConsolePublisher(self.configuration)

    async def run(self) -> None:
        message_request_interval = self.configuration.messages_request_interval
        await self.__do_initial_login(message_request_interval)

        LOG.info("Fetching vehicle list")
        vin_list = await self.saic_api.vehicle_list()

        alarm_switches = list(AlarmType)

        for vin_info in vin_list.vinList:
            await self.setup_vehicle(alarm_switches, vin_info)
        message_handler = MessageHandler(
            gateway=self, relogin_handler=self.__relogin_handler, saicapi=self.saic_api
        )
        self.__scheduler.add_job(
            func=message_handler.check_for_new_messages,
            trigger="interval",
            seconds=message_request_interval,
            id="message_handler",
            name="Check for new messages",
            max_instances=1,
        )
        LOG.info("Connecting to MQTT Broker")
        await self.publisher.connect()

        LOG.info("Starting scheduler")
        self.__scheduler.start()

        LOG.info("Entering main loop")
        await self.__main_loop()

    async def __do_initial_login(self, message_request_interval: int) -> None:
        while True:
            try:
                await self.__relogin_handler.login()
                break
            except Exception as e:
                LOG.exception(
                    "Could not complete initial login to the SAIC API, retrying in %d seconds",
                    message_request_interval,
                    exc_info=e,
                )
                await asyncio.sleep(message_request_interval)

    async def setup_vehicle(
        self, alarm_switches: list[AlarmType], original_vin_info: VinInfo
    ) -> None:
        if not original_vin_info.vin:
            LOG.error("Skipping vehicle setup due to no vin: %s", original_vin_info)
            return

        total_battery_capacity = self.configuration.battery_capacity_map.get(
            original_vin_info.vin, None
        )

        vin_info = VehicleInfo(original_vin_info, total_battery_capacity)

        try:
            LOG.info(
                f"Registering for {[x.name for x in alarm_switches]} messages. vin={vin_info.vin}"
            )
            await self.saic_api.set_alarm_switches(
                alarm_switches=alarm_switches, vin=vin_info.vin
            )
            LOG.info(
                f"Registered for {[x.name for x in alarm_switches]} messages. vin={vin_info.vin}"
            )
        except Exception as e:
            LOG.exception(
                f"Failed to register for {[x.name for x in alarm_switches]} messages. vin={vin_info.vin}",
                exc_info=e,
            )
            raise SystemExit("Failed to register for API messages") from e
        account_prefix = (
            f"{self.configuration.saic_user}/{mqtt_topics.VEHICLES}/{vin_info.vin}"
        )
        charging_station = self.get_charging_station(vin_info.vin)
        if charging_station and charging_station.soc_topic:
            LOG.debug(
                "SoC of %s for charging station will be published over MQTT topic: %s",
                vin_info.vin,
                charging_station.soc_topic,
            )
        if charging_station and charging_station.range_topic:
            LOG.debug(
                "Range of %s for charging station will be published over MQTT topic: %s",
                vin_info.vin,
                charging_station.range_topic,
            )
        vehicle_state = VehicleState(
            self.publisher,
            self.__scheduler,
            account_prefix,
            vin_info,
            charging_station,
            charge_polling_min_percent=self.configuration.charge_dynamic_polling_min_percentage,
        )
        vehicle_handler = VehicleHandler(
            self.configuration,
            self.__relogin_handler,
            self.saic_api,
            self.publisher,  # Gateway pointer
            vin_info,
            vehicle_state,
        )
        self.vehicle_handlers[vin_info.vin] = vehicle_handler

    @override
    def get_vehicle_handler(self, vin: str) -> VehicleHandler | None:
        if vin in self.vehicle_handlers:
            return self.vehicle_handlers[vin]
        LOG.error(f"No vehicle handler found for VIN {vin}")
        return None

    @property
    @override
    def vehicle_handlers(self) -> dict[str, VehicleHandler]:
        return self.__vehicle_handlers

    @override
    async def on_mqtt_command_received(
        self, *, vin: str, topic: str, payload: str
    ) -> None:
        vehicle_handler = self.get_vehicle_handler(vin)
        if vehicle_handler:
            await vehicle_handler.handle_mqtt_command(topic=topic, payload=payload)
        else:
            LOG.debug(f"Command for unknown vin {vin} received")

    @override
    async def on_charging_detected(self, vin: str) -> None:
        vehicle_handler = self.get_vehicle_handler(vin)
        if vehicle_handler:
            # just make sure that we don't set the is_charging flag too early
            # and that it is immediately overwritten by a running vehicle state request
            await asyncio.sleep(delay=3.0)
            vehicle_handler.vehicle_state.set_is_charging(True)
        else:
            LOG.debug(f"Charging detected for unknown vin {vin}")

    @override
    async def on_mqtt_global_command_received(
        self, *, topic: str, payload: str
    ) -> None:
        match topic:
            case self.configuration.ha_lwt_topic:
                if payload == "online":
                    for vin, vh in self.vehicle_handlers.items():
                        # wait randomly between 0.1 and 10 seconds before sending discovery
                        await asyncio.sleep(uniform(0.1, 10.0))  # noqa: S311
                        LOG.debug(f"Send HomeAssistant discovery for car {vin}")
                        vh.publish_ha_discovery_messages(force=True)
            case _:
                LOG.warning(f"Received unknown global command {topic}: {payload}")

    def get_charging_station(self, vin: str) -> ChargingStation | None:
        if vin in self.configuration.charging_stations_by_vin:
            return self.configuration.charging_stations_by_vin[vin]
        return None

    async def __main_loop(self) -> None:
        tasks = []
        for key, vh in self.vehicle_handlers.items():
            LOG.info(f"Starting process for car {key}")
            task = asyncio.create_task(
                vh.handle_vehicle(), name=f"handle_vehicle_{key}"
            )
            tasks.append(task)

        await self.__shutdown_handler(tasks)

    @staticmethod
    async def __shutdown_handler(tasks: list[Task[Any]]) -> None:
        while True:
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                task_name = task.get_name()
                if task.cancelled():
                    LOG.debug(
                        f"{task_name!r} task was cancelled, this is only supposed if the application is "
                        "shutting down"
                    )
                else:
                    exception = task.exception()
                    if exception is not None:
                        LOG.exception(
                            f"{task_name!r} task crashed with an exception",
                            exc_info=exception,
                        )
                        raise SystemExit(-1)
                    LOG.warning(
                        f"{task_name!r} task terminated cleanly with result={task.result()}"
                    )
            if len(pending) == 0:
                break
            LOG.warning(
                f"There are still {len(pending)} tasks... waiting for them to complete"
            )
