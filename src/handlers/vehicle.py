from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
import datetime
import logging
from typing import TYPE_CHECKING

from saic_ismart_client_ng.exceptions import SaicApiException, SaicLogoutException

from handlers.vehicle_command import VehicleCommandHandler
from integrations import IntegrationException
from integrations.abrp.api import AbrpApi
from integrations.home_assistant.discovery import HomeAssistantDiscovery
from integrations.osmand.api import OsmAndApi
import mqtt_topics
from saic_api_listener import MqttGatewayAbrpListener, MqttGatewayOsmAndListener
from status_publisher.vehicle_info import VehicleInfoPublisher

if TYPE_CHECKING:
    from saic_ismart_client_ng import SaicApi
    from saic_ismart_client_ng.api.vehicle.schema import VehicleStatusResp
    from saic_ismart_client_ng.api.vehicle_charging import (
        ChrgMgmtDataResp,
        ScheduledBatteryHeatingResp,
    )

    from configuration import Configuration
    from handlers.relogin import ReloginHandler
    from publisher.core import Publisher
    from status_publisher.charge.chrg_mgmt_data_resp import (
        ChrgMgmtDataRespProcessingResult,
    )
    from status_publisher.vehicle.vehicle_status_resp import (
        VehicleStatusRespProcessingResult,
    )
    from vehicle import VehicleState
    from vehicle_info import VehicleInfo

LOG = logging.getLogger(__name__)


class VehicleHandler:
    def __init__(
        self,
        config: Configuration,
        relogin_handler: ReloginHandler,
        saicapi: SaicApi,
        publisher: Publisher,
        vin_info: VehicleInfo,
        vehicle_state: VehicleState,
    ) -> None:
        self.configuration = config
        self.relogin_handler = relogin_handler
        self.saic_api = saicapi
        self.publisher = publisher
        self.vin_info = vin_info
        self.vehicle_prefix = self.publisher.get_topic(
            f"{self.configuration.saic_user}/vehicles/{self.vin_info.vin}", True
        )
        self.vehicle_state = vehicle_state
        self.__ha_discovery = self.__setup_ha_discovery(vehicle_state, vin_info, config)

        self.__setup_abrp(config, vin_info)
        self.__setup_osmand(config, vin_info)
        self.__vehicle_info_publisher = VehicleInfoPublisher(
            self.vin_info, self.publisher, self.vehicle_prefix
        )
        self.__command_handler = VehicleCommandHandler(
            vehicle_state=vehicle_state,
            saic_api=saicapi,
            relogin_handler=relogin_handler,
            mqtt_topic=self.configuration.mqtt_topic,
            vehicle_prefix=self.vehicle_prefix,
        )

    def __setup_abrp(self, config: Configuration, vin_info: VehicleInfo) -> None:
        if vin_info.vin in self.configuration.abrp_token_map:
            abrp_user_token = self.configuration.abrp_token_map[vin_info.vin]
        else:
            abrp_user_token = None
        if config.publish_raw_abrp_data:
            abrp_api_listener = MqttGatewayAbrpListener(self.publisher)
        else:
            abrp_api_listener = None
        self.abrp_api = AbrpApi(
            self.configuration.abrp_api_key, abrp_user_token, listener=abrp_api_listener
        )

    def __setup_osmand(self, config: Configuration, vin_info: VehicleInfo) -> None:
        if not self.configuration.osmand_server_uri:
            self.osmand_api = None
            return

        if config.publish_raw_osmand_data:
            api_listener = MqttGatewayOsmAndListener(self.publisher)
        else:
            api_listener = None
        osmand_device_id = self.configuration.osmand_device_id_map.get(
            vin_info.vin, vin_info.vin
        )
        self.osmand_api = OsmAndApi(
            server_uri=self.configuration.osmand_server_uri,
            device_id=osmand_device_id,
            listener=api_listener,
        )

    async def handle_vehicle(self) -> None:
        start_time = datetime.datetime.now()
        self.__vehicle_info_publisher.publish()
        self.vehicle_state.notify_car_activity()

        while True:
            if self.__should_complete_configuration(start_time):
                self.vehicle_state.configure_missing()

            if self.__should_poll():
                try:
                    LOG.debug("Polling vehicle status")
                    await self.__polling()
                except SaicLogoutException as e:
                    self.vehicle_state.mark_failed_refresh()
                    LOG.error(
                        "API Client was logged out, waiting for a new login", exc_info=e
                    )
                    self.relogin_handler.relogin()
                except SaicApiException as e:
                    self.vehicle_state.mark_failed_refresh()
                    LOG.exception(
                        "handle_vehicle loop failed during SAIC API call", exc_info=e
                    )
                except IntegrationException as ae:
                    LOG.exception(
                        "handle_vehicle loop failed during integration processing",
                        exc_info=ae,
                    )
                except Exception as e:
                    self.vehicle_state.mark_failed_refresh()
                    LOG.exception(
                        "handle_vehicle loop failed with an unexpected exception",
                        exc_info=e,
                    )
                finally:
                    self.publish_ha_discovery_messages(force=False)
            else:
                # car not active, wait a second
                await asyncio.sleep(1.0)

    async def __polling(self) -> None:
        (
            vehicle_status,
            vehicle_status_processing_result,
        ) = await self.update_vehicle_status()

        charge_status = None
        charge_status_processing_result = None
        if self.vin_info.is_ev:
            try:
                (
                    charge_status,
                    charge_status_processing_result,
                ) = await self.update_charge_status()
            except Exception as e:
                LOG.exception("Error updating charge status", exc_info=e)

            try:
                await self.update_scheduled_battery_heating_status()
            except Exception as e:
                LOG.exception(
                    "Error updating scheduled battery heating status", exc_info=e
                )
        else:
            LOG.debug("Skipping EV-related updates as the vehicle is not an EV")
            charge_status = None

        self.vehicle_state.update_data_conflicting_in_vehicle_and_bms(
            vehicle_status_processing_result, charge_status_processing_result
        )

        self.vehicle_state.mark_successful_refresh()
        LOG.info("Refreshing vehicle status succeeded...")

        await self.__refresh_abrp(charge_status, vehicle_status)
        await self.__refresh_osmand(charge_status, vehicle_status)

    def __should_poll(self) -> bool:
        return (
            not self.relogin_handler.relogin_in_progress
            and self.vehicle_state.is_complete()
            and self.vehicle_state.should_refresh()
        )

    def __should_complete_configuration(self, start_time: datetime.datetime) -> bool:
        return (
            not self.vehicle_state.is_complete()
            and datetime.datetime.now() > start_time + datetime.timedelta(seconds=10)
        )

    async def __refresh_osmand(
        self,
        charge_status: ChrgMgmtDataResp | None,
        vehicle_status: VehicleStatusResp | None,
    ) -> None:
        if not self.osmand_api:
            return
        refreshed, response = await self.osmand_api.update_osmand(
            vehicle_status, charge_status
        )
        self.publisher.publish_str(
            f"{self.vehicle_prefix}/{mqtt_topics.INTERNAL_OSMAND}", response
        )
        if refreshed:
            LOG.info("Refreshing OsmAnd status succeeded...")
        else:
            LOG.info(f"OsmAnd not refreshed, reason {response}")

    async def __refresh_abrp(
        self,
        charge_status: ChrgMgmtDataResp | None,
        vehicle_status: VehicleStatusResp | None,
    ) -> None:
        abrp_refreshed, abrp_response = await self.abrp_api.update_abrp(
            vehicle_status, charge_status
        )
        self.publisher.publish_str(
            f"{self.vehicle_prefix}/{mqtt_topics.INTERNAL_ABRP}", abrp_response
        )
        if abrp_refreshed:
            LOG.info("Refreshing ABRP status succeeded...")
        else:
            LOG.info(f"ABRP not refreshed, reason {abrp_response}")

    def publish_ha_discovery_messages(self, *, force: bool = False) -> None:
        if self.__ha_discovery is not None:
            LOG.info(
                f"Sending HA discovery messages for {self.vin_info.vin} (Force: {force})"
            )
            self.__ha_discovery.publish_ha_discovery_messages(force=force)

    async def update_vehicle_status(
        self,
    ) -> tuple[VehicleStatusResp, VehicleStatusRespProcessingResult]:
        LOG.info("Updating vehicle status")
        vehicle_status_response = await self.saic_api.get_vehicle_status(
            self.vin_info.vin
        )
        result = self.vehicle_state.handle_vehicle_status(vehicle_status_response)
        return (vehicle_status_response, result)

    async def update_charge_status(
        self,
    ) -> tuple[ChrgMgmtDataResp, ChrgMgmtDataRespProcessingResult]:
        LOG.info("Updating charging status")
        charge_mgmt_data = await self.saic_api.get_vehicle_charging_management_data(
            self.vin_info.vin
        )
        result = self.vehicle_state.handle_charge_status(charge_mgmt_data)
        return charge_mgmt_data, result

    async def update_scheduled_battery_heating_status(
        self,
    ) -> ScheduledBatteryHeatingResp:
        LOG.info("Updating scheduled battery heating status")
        scheduled_battery_heating_status = (
            await self.saic_api.get_vehicle_battery_heating_schedule(self.vin_info.vin)
        )
        self.vehicle_state.handle_scheduled_battery_heating_status(
            scheduled_battery_heating_status
        )
        return scheduled_battery_heating_status

    async def handle_mqtt_command(self, *, topic: str, payload: str) -> None:
        await self.__command_handler.handle_mqtt_command(topic=topic, payload=payload)

    def __setup_ha_discovery(
        self, vehicle_state: VehicleState, vin_info: VehicleInfo, config: Configuration
    ) -> HomeAssistantDiscovery | None:
        if self.configuration.ha_discovery_enabled:
            return HomeAssistantDiscovery(vehicle_state, vin_info, config)
        return None


class VehicleHandlerLocator(ABC):
    def get_vehicle_handler(self, vin: str) -> VehicleHandler | None:
        raise NotImplementedError

    @property
    @abstractmethod
    def vehicle_handlers(self) -> dict[str, VehicleHandler]:
        raise NotImplementedError
