from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
import datetime
import json
import logging
from typing import TYPE_CHECKING

from saic_ismart_client_ng.api.vehicle_charging import (
    ChargeCurrentLimitCode,
    ChrgMgmtDataResp,
    ScheduledBatteryHeatingResp,
    ScheduledChargingMode,
    TargetBatteryCode,
)
from saic_ismart_client_ng.exceptions import SaicApiException, SaicLogoutException

from exceptions import MqttGatewayException
from integrations import IntegrationException
from integrations.abrp.api import AbrpApi
from integrations.home_assistant.discovery import HomeAssistantDiscovery
from integrations.osmand.api import OsmAndApi
import mqtt_topics
from mqtt_topics import RESULT_SUFFIX, SET_SUFFIX
from saic_api_listener import MqttGatewayAbrpListener, MqttGatewayOsmAndListener
from status_publisher.vehicle_info import VehicleInfoPublisher
from vehicle import RefreshMode, VehicleState

if TYPE_CHECKING:
    from saic_ismart_client_ng import SaicApi
    from saic_ismart_client_ng.api.vehicle.schema import VehicleStatusResp

    from configuration import Configuration
    from handlers.relogin import ReloginHandler
    from publisher.core import Publisher
    from status_publisher.charge.chrg_mgmt_data_resp import (
        ChrgMgmtDataRespProcessingResult,
    )
    from status_publisher.vehicle.vehicle_status_resp import (
        VehicleStatusRespProcessingResult,
    )
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
        topic, result_topic = self.__get_command_topics(topic)
        try:
            should_force_refresh = True
            match topic:
                case mqtt_topics.DRIVETRAIN_HV_BATTERY_ACTIVE_SET:
                    match payload.strip().lower():
                        case "true":
                            LOG.info("HV battery is now active")
                            self.vehicle_state.hv_battery_active = True
                        case "false":
                            LOG.info("HV battery is now inactive")
                            self.vehicle_state.hv_battery_active = False
                        case _:
                            msg = f"Unsupported payload {payload}"
                            raise MqttGatewayException(msg)
                case mqtt_topics.DRIVETRAIN_CHARGING_SET:
                    match payload.strip().lower():
                        case "true":
                            LOG.info("Charging will be started")
                            await self.saic_api.control_charging(
                                self.vin_info.vin, stop_charging=False
                            )
                        case "false":
                            LOG.info("Charging will be stopped")
                            await self.saic_api.control_charging(
                                self.vin_info.vin, stop_charging=True
                            )
                        case _:
                            msg = f"Unsupported payload {payload}"
                            raise MqttGatewayException(msg)
                case mqtt_topics.DRIVETRAIN_BATTERY_HEATING_SET:
                    match payload.strip().lower():
                        case "true":
                            LOG.info("Battery heater wil be will be switched on")
                            response = await self.saic_api.control_battery_heating(
                                self.vin_info.vin, enable=True
                            )
                        case "false":
                            LOG.info("Battery heater wil be will be switched off")
                            response = await self.saic_api.control_battery_heating(
                                self.vin_info.vin, enable=False
                            )
                        case _:
                            msg = f"Unsupported payload {payload}"
                            raise MqttGatewayException(msg)
                    if response is not None and response.ptcHeatResp is not None:
                        decoded = response.heating_stop_reason
                        self.publisher.publish_str(
                            self.vehicle_state.get_topic(
                                mqtt_topics.DRIVETRAIN_BATTERY_HEATING_STOP_REASON
                            ),
                            f"UNKNOWN ({response.ptcHeatResp})"
                            if decoded is None
                            else decoded.name,
                        )

                case mqtt_topics.CLIMATE_REMOTE_TEMPERATURE_SET:
                    payload = payload.strip()
                    try:
                        LOG.info(
                            "Setting remote climate target temperature to %s", payload
                        )
                        temp = int(payload)
                        changed = self.vehicle_state.set_ac_temperature(temp)
                        if changed and self.vehicle_state.is_remote_ac_running:
                            await self.saic_api.start_ac(
                                self.vin_info.vin,
                                temperature_idx=self.vehicle_state.get_ac_temperature_idx(),
                            )

                    except ValueError as e:
                        msg = f"Error setting temperature target: {e}"
                        raise MqttGatewayException(msg) from e
                case mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE_SET:
                    match payload.strip().lower():
                        case "off":
                            LOG.info("A/C will be switched off")
                            await self.saic_api.stop_ac(self.vin_info.vin)
                        case "blowingonly":
                            LOG.info("A/C will be set to blowing only")
                            await self.saic_api.start_ac_blowing(self.vin_info.vin)
                        case "on":
                            LOG.info("A/C will be switched on")
                            await self.saic_api.start_ac(
                                self.vin_info.vin,
                                temperature_idx=self.vehicle_state.get_ac_temperature_idx(),
                            )
                        case "front":
                            LOG.info("A/C will be set to front seats only")
                            await self.saic_api.start_front_defrost(self.vin_info.vin)
                        case _:
                            msg = f"Unsupported payload {payload}"
                            raise MqttGatewayException(msg)
                case mqtt_topics.CLIMATE_HEATED_SEATS_FRONT_LEFT_LEVEL_SET:
                    try:
                        LOG.info("Setting heated seats front left level to %s", payload)
                        level = int(payload.strip().lower())
                        changed = (
                            self.vehicle_state.update_heated_seats_front_left_level(
                                level
                            )
                        )
                        if changed:
                            await self.saic_api.control_heated_seats(
                                self.vin_info.vin,
                                left_side_level=self.vehicle_state.remote_heated_seats_front_left_level,
                                right_side_level=self.vehicle_state.remote_heated_seats_front_right_level,
                            )
                        else:
                            LOG.info("Heated seats front left level not changed")
                    except Exception as e:
                        msg = f"Error setting heated seats: {e}"
                        raise MqttGatewayException(msg) from e

                case mqtt_topics.CLIMATE_HEATED_SEATS_FRONT_RIGHT_LEVEL_SET:
                    try:
                        LOG.info(
                            "Setting heated seats front right level to %s", payload
                        )
                        level = int(payload.strip().lower())
                        changed = (
                            self.vehicle_state.update_heated_seats_front_right_level(
                                level
                            )
                        )
                        if changed:
                            await self.saic_api.control_heated_seats(
                                self.vin_info.vin,
                                left_side_level=self.vehicle_state.remote_heated_seats_front_left_level,
                                right_side_level=self.vehicle_state.remote_heated_seats_front_right_level,
                            )
                        else:
                            LOG.info("Heated seats front right level not changed")
                    except Exception as e:
                        msg = f"Error setting heated seats: {e}"
                        raise MqttGatewayException(msg) from e

                case mqtt_topics.DOORS_BOOT_SET:
                    match payload.strip().lower():
                        case "true":
                            LOG.info(
                                f"We cannot lock vehicle {self.vin_info.vin} boot remotely"
                            )
                        case "false":
                            LOG.info(
                                f"Vehicle {self.vin_info.vin} boot will be unlocked"
                            )
                            await self.saic_api.open_tailgate(self.vin_info.vin)
                        case _:
                            msg = f"Unsupported payload {payload}"
                            raise MqttGatewayException(msg)
                case mqtt_topics.DOORS_LOCKED_SET:
                    match payload.strip().lower():
                        case "true":
                            LOG.info(f"Vehicle {self.vin_info.vin} will be locked")
                            await self.saic_api.lock_vehicle(self.vin_info.vin)
                        case "false":
                            LOG.info(f"Vehicle {self.vin_info.vin} will be unlocked")
                            await self.saic_api.unlock_vehicle(self.vin_info.vin)
                        case _:
                            msg = f"Unsupported payload {payload}"
                            raise MqttGatewayException(msg)
                case mqtt_topics.CLIMATE_BACK_WINDOW_HEAT_SET:
                    match payload.strip().lower():
                        case "off":
                            LOG.info("Rear window heating will be switched off")
                            await self.saic_api.control_rear_window_heat(
                                self.vin_info.vin, enable=False
                            )
                        case "on":
                            LOG.info("Rear window heating will be switched on")
                            await self.saic_api.control_rear_window_heat(
                                self.vin_info.vin, enable=True
                            )
                        case _:
                            msg = f"Unsupported payload {payload}"
                            raise MqttGatewayException(msg)
                case mqtt_topics.CLIMATE_FRONT_WINDOW_HEAT_SET:
                    match payload.strip().lower():
                        case "off":
                            LOG.info("Front window heating will be switched off")
                            await self.saic_api.stop_ac(self.vin_info.vin)
                        case "on":
                            LOG.info("Front window heating will be switched on")
                            await self.saic_api.start_front_defrost(self.vin_info.vin)
                        case _:
                            msg = f"Unsupported payload {payload}"
                            raise MqttGatewayException(msg)
                case mqtt_topics.DRIVETRAIN_CHARGECURRENT_LIMIT_SET:
                    payload = payload.strip().upper()
                    if self.vehicle_state.target_soc is not None:
                        try:
                            LOG.info("Setting charging current limit to %s", payload)
                            raw_charge_current_limit = str(payload)
                            charge_current_limit = ChargeCurrentLimitCode.to_code(
                                raw_charge_current_limit
                            )
                            await self.saic_api.set_target_battery_soc(
                                self.vin_info.vin,
                                target_soc=self.vehicle_state.target_soc,
                                charge_current_limit=charge_current_limit,
                            )
                            self.vehicle_state.update_charge_current_limit(
                                charge_current_limit
                            )
                        except ValueError as e:
                            msg = f"Error setting value for payload {payload}"
                            raise MqttGatewayException(msg) from e
                    else:
                        LOG.info(
                            "Unknown Target SOC: waiting for state update before changing charge current limit"
                        )
                        msg = f"Error setting charge current limit - SOC {self.vehicle_state.target_soc}"
                        raise MqttGatewayException(msg)
                case mqtt_topics.DRIVETRAIN_SOC_TARGET_SET:
                    payload = payload.strip()
                    try:
                        LOG.info("Setting SoC target to %s", payload)
                        target_battery_code = TargetBatteryCode.from_percentage(
                            int(payload)
                        )
                        await self.saic_api.set_target_battery_soc(
                            self.vin_info.vin, target_soc=target_battery_code
                        )
                        self.vehicle_state.update_target_soc(target_battery_code)
                    except ValueError as e:
                        msg = f"Error setting SoC target: {e}"
                        raise MqttGatewayException(msg) from e
                case mqtt_topics.DRIVETRAIN_CHARGING_SCHEDULE_SET:
                    payload = payload.strip()
                    try:
                        LOG.info("Setting charging schedule to %s", payload)
                        payload_json = json.loads(payload)
                        start_time = datetime.time.fromisoformat(
                            payload_json["startTime"]
                        )
                        end_time = datetime.time.fromisoformat(payload_json["endTime"])
                        mode = ScheduledChargingMode[payload_json["mode"].upper()]
                        await self.saic_api.set_schedule_charging(
                            self.vin_info.vin,
                            start_time=start_time,
                            end_time=end_time,
                            mode=mode,
                        )
                        self.vehicle_state.update_scheduled_charging(start_time, mode)
                    except Exception as e:
                        msg = f"Error setting charging schedule: {e}"
                        raise MqttGatewayException(msg) from e
                case mqtt_topics.DRIVETRAIN_BATTERY_HEATING_SCHEDULE_SET:
                    payload = payload.strip()
                    try:
                        LOG.info("Setting battery heating schedule to %s", payload)
                        payload_json = json.loads(payload)
                        start_time = datetime.time.fromisoformat(
                            payload_json["startTime"]
                        )
                        battery_heating_mode = payload_json["mode"].upper()
                        should_enable = battery_heating_mode == "ON"
                        changed = self.vehicle_state.update_scheduled_battery_heating(
                            start_time, should_enable
                        )
                        if changed:
                            if should_enable:
                                LOG.info(
                                    f"Setting battery heating schedule to {start_time}"
                                )
                                await self.saic_api.enable_schedule_battery_heating(
                                    self.vin_info.vin, start_time=start_time
                                )
                            else:
                                LOG.info("Disabling battery heating schedule")
                                await self.saic_api.disable_schedule_battery_heating(
                                    self.vin_info.vin
                                )
                        else:
                            LOG.info("Battery heating schedule not changed")
                    except Exception as e:
                        msg = f"Error setting battery heating schedule: {e}"
                        raise MqttGatewayException(msg) from e
                case mqtt_topics.DRIVETRAIN_CHARGING_CABLE_LOCK_SET:
                    match payload.strip().lower():
                        case "false":
                            LOG.info(
                                f"Vehicle {self.vin_info.vin} charging cable will be unlocked"
                            )
                            await self.saic_api.control_charging_port_lock(
                                self.vin_info.vin, unlock=True
                            )
                        case "true":
                            LOG.info(
                                f"Vehicle {self.vin_info.vin} charging cable will be locked"
                            )
                            await self.saic_api.control_charging_port_lock(
                                self.vin_info.vin, unlock=False
                            )
                        case _:
                            msg = f"Unsupported payload {payload}"
                            raise MqttGatewayException(msg)
                case mqtt_topics.LOCATION_FIND_MY_CAR_SET:
                    vin = self.vin_info.vin
                    match payload.strip().lower():
                        case "activate":
                            LOG.info(
                                f"Activating 'find my car' with horn and lights for vehicle {vin}"
                            )
                            await self.saic_api.control_find_my_car(vin)
                        case "lights_only":
                            LOG.info(
                                f"Activating 'find my car' with lights only for vehicle {vin}"
                            )
                            await self.saic_api.control_find_my_car(
                                vin, with_horn=False, with_lights=True
                            )
                        case "horn_only":
                            LOG.info(
                                f"Activating 'find my car' with horn only for vehicle {vin}"
                            )
                            await self.saic_api.control_find_my_car(
                                vin, with_horn=True, with_lights=False
                            )
                        case "stop":
                            LOG.info(f"Stopping 'find my car' for vehicle {vin}")
                            await self.saic_api.control_find_my_car(
                                vin, should_stop=True
                            )
                        case _:
                            msg = f"Unsupported payload {payload}"
                            raise MqttGatewayException(msg)
                case _:
                    # set mode, period (in)-active,...
                    should_force_refresh = False
                    await self.vehicle_state.configure_by_message(
                        topic=topic, payload=payload
                    )
            self.publisher.publish_str(result_topic, "Success")
            if should_force_refresh:
                self.vehicle_state.set_refresh_mode(
                    RefreshMode.FORCE, f"after command execution on topic {topic}"
                )
        except MqttGatewayException as e:
            self.publisher.publish_str(result_topic, f"Failed: {e.message}")
            LOG.exception(e.message, exc_info=e)
        except SaicLogoutException as se:
            self.publisher.publish_str(result_topic, f"Failed: {se.message}")
            LOG.error("API Client was logged out, waiting for a new login", exc_info=se)
            self.relogin_handler.relogin()
        except SaicApiException as se:
            self.publisher.publish_str(result_topic, f"Failed: {se.message}")
            LOG.exception(se.message, exc_info=se)
        except Exception as se:
            self.publisher.publish_str(result_topic, "Failed unexpectedly")
            LOG.exception(
                "handle_mqtt_command failed with an unexpected exception", exc_info=se
            )

    def __get_command_topics(self, topic: str) -> tuple[str, str]:
        global_topic_removed = topic.removeprefix(
            self.configuration.mqtt_topic
        ).removeprefix("/")
        set_topic = global_topic_removed.removeprefix(self.vehicle_prefix).removeprefix(
            "/"
        )
        result_topic = (
            global_topic_removed.removesuffix(SET_SUFFIX).removesuffix("/")
            + "/"
            + RESULT_SUFFIX
        )
        return set_topic, result_topic

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
