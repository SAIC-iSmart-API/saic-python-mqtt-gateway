import asyncio
import faulthandler
import logging
import os
import signal
import sys
from typing import override, Optional

import apscheduler.schedulers.asyncio
from saic_ismart_client_ng import SaicApi
from saic_ismart_client_ng.api.vehicle.alarm import AlarmType
from saic_ismart_client_ng.model import SaicApiConfiguration

import mqtt_topics
from configuration import Configuration
from configuration.parser import process_arguments
from handlers.message import MessageHandler
from handlers.relogin import ReloginHandler
from handlers.vehicle import VehicleHandler, VehicleHandlerLocator
from integrations.openwb.charging_station import ChargingStation
from publisher.mqtt_publisher import MqttClient, MqttCommandListener
from saic_api_listener import MqttGatewaySaicApiListener
from vehicle import VehicleState

MSG_CMD_SUCCESSFUL = 'Success'

logging.root.handlers = []
logging.basicConfig(format='{asctime:s} [{levelname:^8s}] {message:s} - {name:s}', style='{')
LOG = logging.getLogger(__name__)
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
LOG.setLevel(level=LOG_LEVEL)
logging.getLogger('apscheduler').setLevel(level=LOG_LEVEL)


def debug_log_enabled():
    return LOG_LEVEL == 'DEBUG'


class MqttGateway(MqttCommandListener, VehicleHandlerLocator):
    def __init__(self, config: Configuration):
        self.configuration = config
        self.__vehicle_handlers: dict[str, VehicleHandler] = dict()
        self.publisher = MqttClient(self.configuration)
        self.publisher.command_listener = self
        username_is_email = "@" in self.configuration.saic_user
        if config.publish_raw_api_data:
            listener = MqttGatewaySaicApiListener(self.publisher)
        else:
            listener = None
        self.saic_api = SaicApi(
            configuration=SaicApiConfiguration(
                username=self.configuration.saic_user,
                password=self.configuration.saic_password,
                username_is_email=username_is_email,
                phone_country_code=None if username_is_email else self.configuration.saic_phone_country_code,
                base_uri=self.configuration.saic_rest_uri,
                region=self.configuration.saic_region,
                tenant_id=self.configuration.saic_tenant_id
            ),
            listener=listener
        )
        self.__scheduler = apscheduler.schedulers.asyncio.AsyncIOScheduler()
        self.__relogin_handler = ReloginHandler(
            relogin_relay=self.configuration.saic_relogin_delay,
            api=self.saic_api,
            scheduler=self.__scheduler
        )

    async def run(self):
        try:
            await self.__relogin_handler.login()
        except Exception as e:
            LOG.exception('MqttGateway crashed due to an Exception during startup', exc_info=e)
            raise SystemExit(e)

        LOG.info("Fetching vehicle list")
        vin_list = await self.saic_api.vehicle_list()

        alarm_switches = [x for x in AlarmType]

        for vin_info in vin_list.vinList:
            try:
                LOG.info(f'Registering for {[x.name for x in alarm_switches]} messages. vin={vin_info.vin}')
                await self.saic_api.set_alarm_switches(alarm_switches=alarm_switches, vin=vin_info.vin)
                LOG.info(f'Registered for {[x.name for x in alarm_switches]} messages. vin={vin_info.vin}')
            except Exception as e:
                LOG.exception(
                    f'Failed to register for {[x.name for x in alarm_switches]} messages. vin={vin_info.vin}',
                    exc_info=e
                )
                raise SystemExit(e)

            account_prefix = f'{self.configuration.saic_user}/{mqtt_topics.VEHICLES}/{vin_info.vin}'
            charging_station = self.get_charging_station(vin_info.vin)
            if (
                    charging_station
                    and charging_station.soc_topic
            ):
                LOG.debug('SoC of %s for charging station will be published over MQTT topic: %s', vin_info.vin,
                          charging_station.soc_topic)
            if (
                    charging_station
                    and charging_station.range_topic
            ):
                LOG.debug('Range of %s for charging station will be published over MQTT topic: %s', vin_info.vin,
                          charging_station.range_topic)
            total_battery_capacity = configuration.battery_capacity_map.get(vin_info.vin, None)
            vehicle_state = VehicleState(
                self.publisher,
                self.__scheduler,
                account_prefix,
                vin_info,
                charging_station,
                charge_polling_min_percent=self.configuration.charge_dynamic_polling_min_percentage,
                total_battery_capacity=total_battery_capacity,
            )

            vehicle_handler = VehicleHandler(
                self.configuration,
                self.__relogin_handler,
                self.saic_api,
                self.publisher,  # Gateway pointer
                vin_info,
                vehicle_state
            )
            self.vehicle_handlers[vin_info.vin] = vehicle_handler
        message_handler = MessageHandler(
            gateway=self,
            relogin_handler=self.__relogin_handler,
            saicapi=self.saic_api
        )
        self.__scheduler.add_job(
            func=message_handler.check_for_new_messages,
            trigger='interval',
            seconds=self.configuration.messages_request_interval,
            id='message_handler',
            name='Check for new messages',
            max_instances=1
        )
        await self.publisher.connect()
        self.__scheduler.start()
        await self.__main_loop()

    @override
    def get_vehicle_handler(self, vin: str) -> Optional[VehicleHandler]:
        if vin in self.vehicle_handlers:
            return self.vehicle_handlers[vin]
        else:
            LOG.error(f'No vehicle handler found for VIN {vin}')
            return None

    @property
    @override
    def vehicle_handlers(self) -> dict[str, VehicleHandler]:
        return self.__vehicle_handlers

    @override
    async def on_mqtt_command_received(self, *, vin: str, topic: str, payload: str) -> None:
        vehicle_handler = self.get_vehicle_handler(vin)
        if vehicle_handler:
            await vehicle_handler.handle_mqtt_command(topic=topic, payload=payload)
        else:
            LOG.debug(f'Command for unknown vin {vin} received')

    @override
    async def on_charging_detected(self, vin: str) -> None:
        vehicle_handler = self.get_vehicle_handler(vin)
        if vehicle_handler:
            # just make sure that we don't set the is_charging flag too early
            # and that it is immediately overwritten by a running vehicle state request
            await asyncio.sleep(delay=3.0)
            vehicle_handler.vehicle_state.set_is_charging(True)
        else:
            LOG.debug(f'Charging detected for unknown vin {vin}')

    def __on_publish_raw_value(self, key: str, raw: str):
        self.publisher.publish_str(key, raw)

    def __on_publish_json_value(self, key: str, json_data: dict):
        self.publisher.publish_json(key, json_data)

    def get_charging_station(self, vin) -> ChargingStation | None:
        if vin in self.configuration.charging_stations_by_vin:
            return self.configuration.charging_stations_by_vin[vin]
        else:
            return None

    async def __main_loop(self):
        tasks = []
        for (key, vh) in self.vehicle_handlers.items():
            LOG.debug(f'Starting process for car {key}')
            task = asyncio.create_task(vh.handle_vehicle(), name=f'handle_vehicle_{key}')
            tasks.append(task)

        await self.__shutdown_handler(tasks)

    @staticmethod
    async def __shutdown_handler(tasks):
        while True:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task_name = task.get_name()
                if task.cancelled():
                    LOG.debug(f'{task_name !r} task was cancelled, this is only supposed if the application is '
                              + 'shutting down')
                else:
                    exception = task.exception()
                    if exception is not None:
                        LOG.exception(f'{task_name !r} task crashed with an exception', exc_info=exception)
                        raise SystemExit(-1)
                    else:
                        LOG.warning(f'{task_name !r} task terminated cleanly with result={task.result()}')
            if len(pending) == 0:
                break
            else:
                LOG.warning(f'There are still {len(pending)} tasks... waiting for them to complete')


if __name__ == '__main__':
    # Enable fault handler to get a thread dump on SIGQUIT
    faulthandler.enable(file=sys.stderr, all_threads=True)
    if hasattr(faulthandler, 'register'):
        faulthandler.register(signal.SIGQUIT, chain=False)
    configuration = process_arguments()

    mqtt_gateway = MqttGateway(configuration)
    asyncio.run(mqtt_gateway.run(), debug=debug_log_enabled())
