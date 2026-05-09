from __future__ import annotations

import asyncio
from asyncio import Task
import contextlib
import datetime
import logging
from random import uniform
import re
from typing import TYPE_CHECKING, Any, override
from zoneinfo import ZoneInfo

import apscheduler.schedulers.asyncio
from saic_ismart_client_ng import SaicApi
from saic_ismart_client_ng.api.vehicle.alarm import AlarmType
from saic_ismart_client_ng.model import SaicApiConfiguration

from exceptions import MqttGatewayException
from handlers.message import MessageHandler
from handlers.relogin import ReloginHandler
from handlers.vehicle import VehicleHandler, VehicleHandlerLocator
from integrations.home_assistant.gateway_discovery import HomeAssistantGatewayDiscovery
import mqtt_topics
from publisher.core import MqttCommandListener, Publisher
from publisher.log_publisher import ConsolePublisher
from publisher.mqtt_publisher import MqttPublisher
from saic_api_listener import MqttGatewaySaicApiListener
from utils import datetime_to_str, get_gateway_version
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
        self.__vehicle_tasks: list[Task[Any]] = []
        self.__user_timezone: ZoneInfo | None = None
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
        self.__account_prefix = f"{self.configuration.saic_user}"
        self.__scheduler = apscheduler.schedulers.asyncio.AsyncIOScheduler()
        self.__relogin_handler = ReloginHandler(
            relogin_relay=self.configuration.saic_relogin_delay,
            api=self.saic_api,
            scheduler=self.__scheduler,
        )
        self.__gateway_discovery = self.__setup_gateway_discovery()

    def __setup_gateway_discovery(self) -> HomeAssistantGatewayDiscovery | None:
        if self.configuration.ha_discovery_enabled:
            return HomeAssistantGatewayDiscovery(
                publisher=self.publisher,
                account_prefix=self.__account_prefix,
                discovery_prefix=self.configuration.ha_discovery_prefix,
            )
        return None

    def __select_publisher(self) -> Publisher:
        if self.configuration.is_mqtt_enabled:
            return MqttPublisher(self.configuration)
        LOG.warning("MQTT support disabled")
        return ConsolePublisher(self.configuration)

    async def run(self) -> None:
        LOG.info("Connecting to MQTT Broker")
        await self.publisher.connect()

        self.__relogin_handler.add_post_login_callback(self.__on_login_success)
        self.__relogin_handler.add_post_login_callback(self.__refresh_account_data)
        self.__relogin_handler.add_login_failure_callback(self.__on_login_failure)

        message_request_interval = self.configuration.messages_request_interval
        await self.__do_initial_login(message_request_interval)

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

        self.__scheduler.add_job(
            func=self.__refresh_account_data,
            trigger="interval",
            seconds=self.configuration.account_refresh_interval,
            id="account_refresh",
            name="Refresh account data",
            max_instances=1,
        )

        # We defer this later in the process so that we can properly configure the gateway and each car via MQTT
        LOG.info("Enabling MQTT command handling")
        self.publisher.enable_commands()

        LOG.info("Starting scheduler")
        self.__scheduler.start()

        LOG.info("Entering main loop")
        await self.__run_until_all_tasks_done()

    @staticmethod
    def __parse_timezone(tz_str: str) -> ZoneInfo:
        try:
            return ZoneInfo(tz_str)
        except (KeyError, ModuleNotFoundError):
            pass

        # Handle GMT+HH:MM / GMT-HH:MM format from the SAIC API.
        # POSIX Etc/GMT zones use inverted signs: GMT+01:00 → Etc/GMT-1
        m = re.fullmatch(r"GMT([+-])(\d{2}):(\d{2})", tz_str)
        if m:
            sign, hours, minutes = m.group(1), int(m.group(2)), int(m.group(3))
            if minutes != 0:
                LOG.warning(
                    "Timezone %s has non-zero minutes, rounding to whole hour", tz_str
                )
            posix_sign = "-" if sign == "+" else "+"
            return ZoneInfo(f"Etc/GMT{posix_sign}{hours}")

        msg = f"Unrecognized timezone format: {tz_str}"
        raise ValueError(msg)

    async def __fetch_user_timezone(self) -> ZoneInfo | None:
        try:
            resp = await self.saic_api.get_user_timezone()
            if resp.timezone:
                tz = self.__parse_timezone(resp.timezone)
                LOG.info("User timezone from API: %s → %s", resp.timezone, tz)
                return tz
            LOG.warning("API returned no timezone, using system default")
        except Exception:
            LOG.warning(
                "Failed to fetch user timezone, using system default", exc_info=True
            )
        return None

    def __get_account_topic(self, topic: str) -> str:
        return f"{self.__account_prefix}/{topic}"

    def __publish_account_str(self, topic: str, value: str) -> None:
        self.publisher.publish_str(self.__get_account_topic(topic), value)

    def __publish_account_int(self, topic: str, value: int) -> None:
        self.publisher.publish_int(self.__get_account_topic(topic), value)

    async def __refresh_user_timezone(self) -> None:
        tz = await self.__fetch_user_timezone()
        if tz is not None:
            self.__user_timezone = tz
            for vh in self.vehicle_handlers.values():
                vh.vehicle_state.update_user_timezone(tz)
        tz_str = (
            str(self.__user_timezone) if self.__user_timezone is not None else "unknown"
        )
        self.__publish_account_str(mqtt_topics.ACCOUNT_USER_TIMEZONE, tz_str)

    async def __on_login_success(self) -> None:
        now = datetime_to_str(datetime.datetime.now(tz=datetime.UTC))
        self.__publish_account_str(mqtt_topics.ACCOUNT_LAST_LOGIN, now)

    async def __on_login_failure(self) -> None:
        now = datetime_to_str(datetime.datetime.now(tz=datetime.UTC))
        self.__publish_account_str(mqtt_topics.ACCOUNT_LAST_LOGIN_ERROR, now)

    async def __refresh_account_data(self) -> None:
        await self.__refresh_vehicle_list()
        await self.__refresh_user_timezone()
        self.__publish_account_str(
            mqtt_topics.ACCOUNT_GATEWAY_VERSION,
            get_gateway_version(),
        )
        self.__publish_account_int(
            mqtt_topics.ACCOUNT_REFRESH_INTERVAL,
            self.configuration.account_refresh_interval,
        )
        self.__publish_account_str(
            mqtt_topics.ACCOUNT_LAST_REFRESH,
            datetime_to_str(datetime.datetime.now(tz=datetime.UTC)),
        )
        self.__publish_gateway_discovery()

    def __publish_gateway_discovery(self) -> None:
        if self.__gateway_discovery is not None:
            self.__gateway_discovery.publish_ha_discovery_messages()

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

        while not self.__vehicle_tasks:
            LOG.warning(
                "No vehicles were set up, retrying discovery in %d seconds",
                message_request_interval,
            )
            await asyncio.sleep(message_request_interval)
            await self.__refresh_vehicle_list()

    async def __register_alarm_switches(
        self, alarm_switches: list[AlarmType], vin: str
    ) -> None:
        LOG.info(
            f"Registering for {[x.name for x in alarm_switches]} messages. vin={vin}"
        )
        await self.saic_api.set_alarm_switches(alarm_switches=alarm_switches, vin=vin)
        LOG.info(
            f"Registered for {[x.name for x in alarm_switches]} messages. vin={vin}"
        )

    def __create_vehicle_handler(self, vin_info: VinInfo) -> VehicleHandler:
        vin = vin_info.vin
        total_battery_capacity = (
            self.configuration.battery_capacity_map.get(vin, None) if vin else None
        )
        info = VehicleInfo(vin_info, total_battery_capacity)
        account_prefix = f"{self.configuration.saic_user}/{mqtt_topics.VEHICLES}/{vin}"
        vehicle_state = VehicleState(
            self.publisher,
            self.__scheduler,
            account_prefix,
            info,
            charge_polling_min_percent=self.configuration.charge_dynamic_polling_min_percentage,
            user_timezone=self.__user_timezone,
        )
        return VehicleHandler(
            self.configuration,
            self.__relogin_handler,
            self.saic_api,
            self.publisher,
            info,
            vehicle_state,
        )

    async def __refresh_vehicle_list(self) -> None:
        LOG.info("Refreshing vehicle list")
        try:
            vin_list = await self.saic_api.vehicle_list()
        except Exception:
            LOG.warning("Failed to refresh vehicle list", exc_info=True)
            return

        alarm_switches = list(AlarmType)
        known_vins = set(self.vehicle_handlers.keys())
        api_vins = {v.vin for v in vin_list.vinList if v.vin}

        # Re-register alarm switches for existing vehicles
        for vin in known_vins & api_vins:
            try:
                await self.__register_alarm_switches(alarm_switches, vin)
            except Exception:
                LOG.warning(
                    "Failed to re-register alarm switches for vin=%s",
                    vin,
                    exc_info=True,
                )

        # Set up new vehicles
        for vin_info in vin_list.vinList:
            if vin_info.vin and vin_info.vin not in known_vins:
                LOG.info("Setting up vehicle: %s", vin_info.vin)
                try:
                    await self.__register_alarm_switches(alarm_switches, vin_info.vin)
                    vh = self.__create_vehicle_handler(vin_info)
                    self.vehicle_handlers[vin_info.vin] = vh
                    self.__start_vehicle_task(vh)
                except Exception:
                    LOG.warning(
                        "Failed to set up new vehicle %s", vin_info.vin, exc_info=True
                    )

        # Stop polling removed vehicles and mark them unavailable
        for vin in known_vins - api_vins:
            LOG.warning("Vehicle %s no longer in API vehicle list, stopping", vin)
            vh = self.vehicle_handlers.pop(vin)
            vh.vehicle_state.mark_failed_refresh()
            task = self.__cancel_vehicle_task(vin)
            if task is not None:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            await vh.close()

    def __start_vehicle_task(self, vh: VehicleHandler) -> None:
        vin = vh.vin_info.vin
        task = asyncio.create_task(vh.handle_vehicle(), name=f"handle_vehicle_{vin}")
        self.__vehicle_tasks.append(task)
        LOG.info("Started polling task for vehicle %s", vin)

    def __cancel_vehicle_task(self, vin: str) -> Task[Any] | None:
        task_name = f"handle_vehicle_{vin}"
        cancelled_task = None
        remaining = []
        for t in self.__vehicle_tasks:
            if t.get_name() == task_name:
                t.cancel()
                cancelled_task = t
            else:
                remaining.append(t)
        self.__vehicle_tasks = remaining
        return cancelled_task

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
        self, *, vin: str, topic: str, payload: str, retained: bool = False
    ) -> None:
        vehicle_handler = self.get_vehicle_handler(vin)
        if vehicle_handler:
            await vehicle_handler.handle_mqtt_command(
                topic=topic, payload=payload, retained=retained
            )
        elif retained:
            LOG.warning(
                f"Retained command for unknown vin {vin} received on {topic};"
                f" handler not yet registered, dropping replay"
            )
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
    async def on_charging_station_energy_imported(
        self, vin: str, imported_energy_wh: float
    ) -> None:
        vehicle_handler = self.get_vehicle_handler(vin)
        if vehicle_handler:
            vehicle_handler.handle_charging_station_energy_imported(imported_energy_wh)
        else:
            LOG.debug(f"Energy imported for unknown vin {vin}")

    @override
    async def on_charger_connection_state_changed(
        self, vin: str, connected: bool
    ) -> None:
        vehicle_handler = self.get_vehicle_handler(vin)
        if vehicle_handler:
            vehicle_handler.handle_charger_connection_state_changed(connected)
        else:
            LOG.debug(f"Charger connection state changed for unknown vin {vin}")

    @override
    def on_mqtt_reconnected(self) -> None:
        LOG.info("MQTT reconnected, resetting HA discovery for all vehicles")
        if self.__gateway_discovery is not None:
            self.__gateway_discovery.reset()
        for vin, vh in self.vehicle_handlers.items():
            LOG.debug(f"Resetting HA discovery for vehicle {vin}")
            vh.reset_ha_discovery()

    @override
    async def on_mqtt_global_command_received(
        self, *, topic: str, payload: str
    ) -> None:
        match topic:
            case self.configuration.ha_lwt_topic:
                if payload == "online":
                    await asyncio.sleep(uniform(0.1, 10.0))  # noqa: S311
                    self.__publish_gateway_discovery()
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

    async def __run_until_all_tasks_done(self) -> None:
        while True:
            # Clean up completed tasks
            self.__vehicle_tasks = [t for t in self.__vehicle_tasks if not t.done()]
            if not self.__vehicle_tasks:
                await asyncio.sleep(1.0)
                continue

            done, _pending = await asyncio.wait(
                self.__vehicle_tasks, return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                task_name = task.get_name()
                if task.cancelled():
                    LOG.debug(f"{task_name!r} task was cancelled")
                elif (exception := task.exception()) is not None:
                    LOG.exception(
                        f"{task_name!r} task crashed with an exception",
                        exc_info=exception,
                    )
                    raise SystemExit(-1)
                else:
                    LOG.warning(
                        f"{task_name!r} task terminated cleanly with result={task.result()}"
                    )
