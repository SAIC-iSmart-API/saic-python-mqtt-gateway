from __future__ import annotations

from datetime import time
import json
import logging
from typing import TYPE_CHECKING, Final

from saic_ismart_client_ng.api.vehicle_charging import (
    ChargeCurrentLimitCode,
    ScheduledChargingMode,
    TargetBatteryCode,
)
from saic_ismart_client_ng.exceptions import SaicApiException, SaicLogoutException

from exceptions import MqttGatewayException
import mqtt_topics
from vehicle import RefreshMode

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from saic_ismart_client_ng import SaicApi

    from handlers.relogin import ReloginHandler
    from publisher.core import Publisher
    from vehicle import VehicleState

    CommandHandler = Callable[[str], Awaitable[bool]]

LOG = logging.getLogger(__name__)


class MqttCommandHandler:
    def __init__(
        self,
        *,
        vehicle_state: VehicleState,
        saic_api: SaicApi,
        relogin_handler: ReloginHandler,
        mqtt_topic: str,
        vehicle_prefix: str,
    ) -> None:
        self.vehicle_state: Final[VehicleState] = vehicle_state
        self.saic_api: Final[SaicApi] = saic_api
        self.relogin_handler: Final[ReloginHandler] = relogin_handler
        self.global_mqtt_topic: Final[str] = mqtt_topic
        self.vehicle_prefix: Final[str] = vehicle_prefix
        self.__command_handlers: dict[str, CommandHandler] = {
            mqtt_topics.DRIVETRAIN_HV_BATTERY_ACTIVE_SET: self.__handle_battery_active,
            mqtt_topics.DRIVETRAIN_CHARGING_SET: self.__handle_charging,
            mqtt_topics.DRIVETRAIN_BATTERY_HEATING_SET: self.__handle_battery_heating,
            mqtt_topics.CLIMATE_REMOTE_TEMPERATURE_SET: self.__handle_remote_temperature,
            mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE_SET: self.__handle_remote_climate,
            mqtt_topics.CLIMATE_HEATED_SEATS_FRONT_LEFT_LEVEL_SET: self.__handle_heated_seats_front_left,
            mqtt_topics.CLIMATE_HEATED_SEATS_FRONT_RIGHT_LEVEL_SET: self.__handle_heated_seats_front_right,
            mqtt_topics.DOORS_BOOT_SET: self.__handle_doors_boot,
            mqtt_topics.DOORS_LOCKED_SET: self.__handle_doors_locked,
            mqtt_topics.CLIMATE_BACK_WINDOW_HEAT_SET: self.__handle_climate_back_window,
            mqtt_topics.CLIMATE_FRONT_WINDOW_HEAT_SET: self.__handle_climate_front_window,
            mqtt_topics.DRIVETRAIN_CHARGECURRENT_LIMIT_SET: self.__handle_charge_current_limit,
            mqtt_topics.DRIVETRAIN_SOC_TARGET_SET: self.__handle_soc_target,
            mqtt_topics.DRIVETRAIN_CHARGING_SCHEDULE_SET: self.__handle_charging_schedule,
            mqtt_topics.DRIVETRAIN_BATTERY_HEATING_SCHEDULE_SET: self.__handle_battery_heating_schedule,
            mqtt_topics.DRIVETRAIN_CHARGING_CABLE_LOCK_SET: self.__handle_charging_cable_lock,
            mqtt_topics.LOCATION_FIND_MY_CAR_SET: self.__handle_find_my_car,
            mqtt_topics.REFRESH_MODE_SET: self.__handle_refresh_mode,
            mqtt_topics.REFRESH_PERIOD_ACTIVE_SET: self.__handle_refresh_period_active,
            mqtt_topics.REFRESH_PERIOD_INACTIVE_SET: self.__handle_refresh_period_inactive,
            mqtt_topics.REFRESH_PERIOD_AFTER_SHUTDOWN_SET: self.__handle_refresh_period_after_shutdown,
            mqtt_topics.REFRESH_PERIOD_INACTIVE_GRACE_SET: self.__handle_refresh_period_inactive_grace,
        }

    @property
    def vin(self) -> str:
        return self.vehicle_state.vin

    @property
    def publisher(self) -> Publisher:
        return self.vehicle_state.publisher

    async def handle_mqtt_command(self, *, topic: str, payload: str) -> None:
        topic, result_topic = self.__get_command_topics(topic)
        handler = self.__command_handlers.get(topic)
        if not handler:
            msg = f"No handler found for command topic {topic}"
            self.publisher.publish_str(result_topic, msg)
            LOG.error(msg)
        else:
            await self.__execute_mqtt_command_handler(
                handler=handler, payload=payload, topic=topic, result_topic=result_topic
            )

    async def __execute_mqtt_command_handler(
        self,
        *,
        handler: CommandHandler,
        payload: str,
        topic: str,
        result_topic: str,
    ) -> None:
        try:
            should_force_refresh = await handler(payload)
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

    async def __handle_find_my_car(self, payload: str) -> bool:
        vin = self.vin
        match payload.strip().lower():
            case "activate":
                LOG.info(
                    f"Activating 'find my car' with horn and lights for vehicle {vin}"
                )
                await self.saic_api.control_find_my_car(vin)
            case "lights_only":
                LOG.info(f"Activating 'find my car' with lights only for vehicle {vin}")
                await self.saic_api.control_find_my_car(
                    vin, with_horn=False, with_lights=True
                )
            case "horn_only":
                LOG.info(f"Activating 'find my car' with horn only for vehicle {vin}")
                await self.saic_api.control_find_my_car(
                    vin, with_horn=True, with_lights=False
                )
            case "stop":
                LOG.info(f"Stopping 'find my car' for vehicle {vin}")
                await self.saic_api.control_find_my_car(vin, should_stop=True)
            case _:
                msg = f"Unsupported payload {payload}"
                raise MqttGatewayException(msg)
        return True

    async def __handle_charging_cable_lock(self, payload: str) -> bool:
        match payload.strip().lower():
            case "false":
                LOG.info(f"Vehicle {self.vin} charging cable will be unlocked")
                await self.saic_api.control_charging_port_lock(self.vin, unlock=True)
            case "true":
                LOG.info(f"Vehicle {self.vin} charging cable will be locked")
                await self.saic_api.control_charging_port_lock(self.vin, unlock=False)
            case _:
                msg = f"Unsupported payload {payload}"
                raise MqttGatewayException(msg)
        return True

    async def __handle_battery_heating_schedule(self, payload: str) -> bool:
        payload = payload.strip()
        try:
            LOG.info("Setting battery heating schedule to %s", payload)
            payload_json = json.loads(payload)
            start_time = time.fromisoformat(payload_json["startTime"])
            battery_heating_mode = payload_json["mode"].upper()
            should_enable = battery_heating_mode == "ON"
            changed = self.vehicle_state.update_scheduled_battery_heating(
                start_time, should_enable
            )
            if changed:
                if should_enable:
                    LOG.info(f"Setting battery heating schedule to {start_time}")
                    await self.saic_api.enable_schedule_battery_heating(
                        self.vin, start_time=start_time
                    )
                else:
                    LOG.info("Disabling battery heating schedule")
                    await self.saic_api.disable_schedule_battery_heating(self.vin)
            else:
                LOG.info("Battery heating schedule not changed")
        except Exception as e:
            msg = f"Error setting battery heating schedule: {e}"
            raise MqttGatewayException(msg) from e
        return True

    async def __handle_charging_schedule(self, payload: str) -> bool:
        payload = payload.strip()
        try:
            LOG.info("Setting charging schedule to %s", payload)
            payload_json = json.loads(payload)
            start_time = time.fromisoformat(payload_json["startTime"])
            end_time = time.fromisoformat(payload_json["endTime"])
            mode = ScheduledChargingMode[payload_json["mode"].upper()]
            await self.saic_api.set_schedule_charging(
                self.vin,
                start_time=start_time,
                end_time=end_time,
                mode=mode,
            )
            self.vehicle_state.update_scheduled_charging(start_time, mode)
        except Exception as e:
            msg = f"Error setting charging schedule: {e}"
            raise MqttGatewayException(msg) from e
        return True

    async def __handle_soc_target(self, payload: str) -> bool:
        payload = payload.strip()
        try:
            LOG.info("Setting SoC target to %s", payload)
            target_battery_code = TargetBatteryCode.from_percentage(int(payload))
            await self.saic_api.set_target_battery_soc(
                self.vin, target_soc=target_battery_code
            )
            self.vehicle_state.update_target_soc(target_battery_code)
        except ValueError as e:
            msg = f"Error setting SoC target: {e}"
            raise MqttGatewayException(msg) from e
        return True

    async def __handle_charge_current_limit(self, payload: str) -> bool:
        payload = payload.strip().upper()
        if self.vehicle_state.target_soc is not None:
            try:
                LOG.info("Setting charging current limit to %s", payload)
                raw_charge_current_limit = str(payload)
                charge_current_limit = ChargeCurrentLimitCode.to_code(
                    raw_charge_current_limit
                )
                await self.saic_api.set_target_battery_soc(
                    self.vin,
                    target_soc=self.vehicle_state.target_soc,
                    charge_current_limit=charge_current_limit,
                )
                self.vehicle_state.update_charge_current_limit(charge_current_limit)
                return True
            except ValueError as e:
                msg = f"Error setting value for payload {payload}"
                raise MqttGatewayException(msg) from e
        else:
            LOG.info(
                "Unknown Target SOC: waiting for state update before changing charge current limit"
            )
            msg = f"Error setting charge current limit - SOC {self.vehicle_state.target_soc}"
            raise MqttGatewayException(msg)

    async def __handle_climate_front_window(self, payload: str) -> bool:
        match payload.strip().lower():
            case "off":
                LOG.info("Front window heating will be switched off")
                await self.saic_api.stop_ac(self.vin)
            case "on":
                LOG.info("Front window heating will be switched on")
                await self.saic_api.start_front_defrost(self.vin)
            case _:
                msg = f"Unsupported payload {payload}"
                raise MqttGatewayException(msg)
        return True

    async def __handle_climate_back_window(self, payload: str) -> bool:
        match payload.strip().lower():
            case "off":
                LOG.info("Rear window heating will be switched off")
                await self.saic_api.control_rear_window_heat(self.vin, enable=False)
            case "on":
                LOG.info("Rear window heating will be switched on")
                await self.saic_api.control_rear_window_heat(self.vin, enable=True)
            case _:
                msg = f"Unsupported payload {payload}"
                raise MqttGatewayException(msg)
        return True

    async def __handle_doors_locked(self, payload: str) -> bool:
        match payload.strip().lower():
            case "true":
                LOG.info(f"Vehicle {self.vin} will be locked")
                await self.saic_api.lock_vehicle(self.vin)
            case "false":
                LOG.info(f"Vehicle {self.vin} will be unlocked")
                await self.saic_api.unlock_vehicle(self.vin)
            case _:
                msg = f"Unsupported payload {payload}"
                raise MqttGatewayException(msg)
        return True

    async def __handle_doors_boot(self, payload: str) -> bool:
        match payload.strip().lower():
            case "true":
                LOG.info(f"We cannot lock vehicle {self.vin} boot remotely")
            case "false":
                LOG.info(f"Vehicle {self.vin} boot will be unlocked")
                await self.saic_api.open_tailgate(self.vin)
            case _:
                msg = f"Unsupported payload {payload}"
                raise MqttGatewayException(msg)
        return True

    async def __handle_heated_seats_front_right(self, payload: str) -> bool:
        try:
            LOG.info("Setting heated seats front right level to %s", payload)
            level = int(payload.strip().lower())
            changed = self.vehicle_state.update_heated_seats_front_right_level(level)
            if changed:
                await self.saic_api.control_heated_seats(
                    self.vin,
                    left_side_level=self.vehicle_state.remote_heated_seats_front_left_level,
                    right_side_level=self.vehicle_state.remote_heated_seats_front_right_level,
                )
            else:
                LOG.info("Heated seats front right level not changed")
        except Exception as e:
            msg = f"Error setting heated seats: {e}"
            raise MqttGatewayException(msg) from e
        return True

    async def __handle_heated_seats_front_left(self, payload: str) -> bool:
        try:
            LOG.info("Setting heated seats front left level to %s", payload)
            level = int(payload.strip().lower())
            changed = self.vehicle_state.update_heated_seats_front_left_level(level)
            if changed:
                await self.saic_api.control_heated_seats(
                    self.vin,
                    left_side_level=self.vehicle_state.remote_heated_seats_front_left_level,
                    right_side_level=self.vehicle_state.remote_heated_seats_front_right_level,
                )
            else:
                LOG.info("Heated seats front left level not changed")
        except Exception as e:
            msg = f"Error setting heated seats: {e}"
            raise MqttGatewayException(msg) from e
        return True

    async def __handle_remote_climate(self, payload: str) -> bool:
        match payload.strip().lower():
            case "off":
                LOG.info("A/C will be switched off")
                await self.saic_api.stop_ac(self.vin)
            case "blowingonly":
                LOG.info("A/C will be set to blowing only")
                await self.saic_api.start_ac_blowing(self.vin)
            case "on":
                LOG.info("A/C will be switched on")
                await self.saic_api.start_ac(
                    self.vin,
                    temperature_idx=self.vehicle_state.get_ac_temperature_idx(),
                )
            case "front":
                LOG.info("A/C will be set to front seats only")
                await self.saic_api.start_front_defrost(self.vin)
            case _:
                msg = f"Unsupported payload {payload}"
                raise MqttGatewayException(msg)
        return True

    async def __handle_remote_temperature(self, payload: str) -> bool:
        payload = payload.strip()
        try:
            LOG.info("Setting remote climate target temperature to %s", payload)
            temp = int(payload)
            changed = self.vehicle_state.set_ac_temperature(temp)
            if changed and self.vehicle_state.is_remote_ac_running:
                await self.saic_api.start_ac(
                    self.vin,
                    temperature_idx=self.vehicle_state.get_ac_temperature_idx(),
                )

        except ValueError as e:
            msg = f"Error setting temperature target: {e}"
            raise MqttGatewayException(msg) from e
        return True

    async def __handle_battery_heating(self, payload: str) -> bool:
        match payload.strip().lower():
            case "true" | "1" | "on":
                LOG.info("Battery heater wil be will be switched on")
                response = await self.saic_api.control_battery_heating(
                    self.vin, enable=True
                )
            case "false" | "0" | "off":
                LOG.info("Battery heater wil be will be switched off")
                response = await self.saic_api.control_battery_heating(
                    self.vin, enable=False
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
        return True

    async def __handle_charging(self, payload: str) -> bool:
        match payload.strip().lower():
            case "true":
                LOG.info("Charging will be started")
                await self.saic_api.control_charging(self.vin, stop_charging=False)
            case "false":
                LOG.info("Charging will be stopped")
                await self.saic_api.control_charging(self.vin, stop_charging=True)
            case _:
                msg = f"Unsupported payload {payload}"
                raise MqttGatewayException(msg)
        return True

    async def __handle_battery_active(self, payload: str) -> bool:
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
        return True

    async def __handle_refresh_period_inactive_grace(self, payload: str) -> bool:
        payload = payload.strip().lower()
        try:
            seconds = int(payload)
            self.vehicle_state.set_refresh_period_inactive_grace(seconds)
        except ValueError as e:
            msg = f"Error setting value for payload {payload}"
            raise MqttGatewayException(msg) from e
        return False

    async def __handle_refresh_period_after_shutdown(self, payload: str) -> bool:
        payload = payload.strip().lower()
        try:
            seconds = int(payload)
            self.vehicle_state.set_refresh_period_after_shutdown(seconds)
        except ValueError as e:
            msg = f"Error setting value for payload {payload}"
            raise MqttGatewayException(msg) from e
        return False

    async def __handle_refresh_period_inactive(self, payload: str) -> bool:
        payload = payload.strip().lower()
        try:
            seconds = int(payload)
            self.vehicle_state.set_refresh_period_inactive(seconds)
        except ValueError as e:
            msg = f"Error setting value for paylo d {payload}"
            raise MqttGatewayException(msg) from e
        return False

    async def __handle_refresh_period_active(self, payload: str) -> bool:
        payload = payload.strip().lower()
        try:
            seconds = int(payload)
            self.vehicle_state.set_refresh_period_active(seconds)
        except ValueError as e:
            msg = f"Error setting value for payload {payload}"
            raise MqttGatewayException(msg) from e
        return False

    async def __handle_refresh_mode(self, payload: str) -> bool:
        payload = payload.strip().lower()
        try:
            refresh_mode = RefreshMode.get(payload)
            self.vehicle_state.set_refresh_mode(
                refresh_mode, "MQTT direct set refresh mode command execution"
            )
        except KeyError as e:
            msg = f"Unsupported payload {payload}"
            raise MqttGatewayException(msg) from e
        return False

    def __get_command_topics(self, topic: str) -> tuple[str, str]:
        global_topic_removed = topic.removeprefix(self.global_mqtt_topic).removeprefix(
            "/"
        )
        set_topic = global_topic_removed.removeprefix(self.vehicle_prefix).removeprefix(
            "/"
        )
        result_topic = (
            global_topic_removed.removesuffix(mqtt_topics.SET_SUFFIX).removesuffix("/")
            + "/"
            + mqtt_topics.RESULT_SUFFIX
        )
        return set_topic, result_topic
