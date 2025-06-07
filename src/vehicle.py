from __future__ import annotations

import datetime
from enum import Enum, unique
import logging
import math
from typing import TYPE_CHECKING, Any, Final, TypeVar

from apscheduler.triggers.cron import CronTrigger
from saic_ismart_client_ng.api.vehicle_charging import (
    ChargeCurrentLimitCode,
    ChrgMgmtDataResp,
    ScheduledBatteryHeatingResp,
    ScheduledChargingMode,
    TargetBatteryCode,
)

from exceptions import MqttGatewayException
import mqtt_topics
from status_publisher.charge.chrg_mgmt_data_resp import (
    ChrgMgmtDataRespProcessingResult,
    ChrgMgmtDataRespPublisher,
)
from status_publisher.message import MessagePublisher
from status_publisher.vehicle.vehicle_status_resp import (
    VehicleStatusRespProcessingResult,
    VehicleStatusRespPublisher,
)
from utils import datetime_to_str, value_in_range

if TYPE_CHECKING:
    from collections.abc import Callable

    from apscheduler.job import Job
    from apscheduler.schedulers.base import BaseScheduler
    from saic_ismart_client_ng.api.message.schema import MessageEntity
    from saic_ismart_client_ng.api.vehicle import (
        VehicleStatusResp,
    )

    from integrations.openwb.charging_station import ChargingStation
    from publisher.core import Publisher
    from vehicle_info import VehicleInfo

    T = TypeVar("T")
    Publishable = TypeVar(
        "Publishable", str, int, float, bool, dict[str, Any], datetime.datetime
    )

DEFAULT_AC_TEMP = 22
PRESSURE_TO_BAR_FACTOR = 0.04

LOG = logging.getLogger(__name__)


@unique
class RefreshMode(Enum):
    FORCE = "force"
    OFF = "off"
    PERIODIC = "periodic"

    @staticmethod
    def get(mode: str) -> RefreshMode:
        return RefreshMode[mode.upper()]


class VehicleState:
    def __init__(
        self,
        publisher: Publisher,
        scheduler: BaseScheduler,
        account_prefix: str,
        vin_info: VehicleInfo,
        charging_station: ChargingStation | None = None,
        charge_polling_min_percent: float = 1.0,
    ) -> None:
        self.publisher = publisher
        self.__message_publisher = MessagePublisher(vin_info, publisher, account_prefix)
        self.__vehicle_response_publisher = VehicleStatusRespPublisher(
            vin_info, publisher, account_prefix
        )
        self.__charge_response_publisher = ChrgMgmtDataRespPublisher(
            vin_info, publisher, account_prefix
        )
        self.vehicle: Final[VehicleInfo] = vin_info
        self.mqtt_vin_prefix = account_prefix
        self.charging_station = charging_station
        self.last_car_activity: datetime.datetime = datetime.datetime.min
        self.last_successful_refresh: datetime.datetime = datetime.datetime.min
        self.__last_failed_refresh: datetime.datetime | None = None
        self.__failed_refresh_counter = 0
        self.__refresh_period_error = 30
        self.last_car_shutdown: datetime.datetime = datetime.datetime.now()
        self.last_car_vehicle_message: datetime.datetime = datetime.datetime.min
        # treat high voltage battery as active, if we don't have any other information
        self.__hv_battery_active = True
        self.__hv_battery_active_from_car = True
        self.is_charging = False
        self.refresh_period_active = -1
        self.refresh_period_inactive = -1
        self.refresh_period_after_shutdown = -1
        self.refresh_period_inactive_grace = -1
        self.target_soc: TargetBatteryCode | None = None
        self.charge_current_limit: ChargeCurrentLimitCode | None = None
        self.refresh_period_charging = 0
        self.charge_polling_min_percent = charge_polling_min_percent
        self.refresh_mode = RefreshMode.OFF
        self.previous_refresh_mode = RefreshMode.OFF
        self.__remote_ac_temp: int | None = None
        self.__remote_ac_running: bool = False
        self.__remote_heated_seats_front_left_level: int = 0
        self.__remote_heated_seats_front_right_level: int = 0
        self.__scheduler = scheduler
        self.__scheduled_battery_heating_enabled = False
        self.__scheduled_battery_heating_start: datetime.time | None = None

    def set_refresh_period_active(self, seconds: int) -> None:
        if seconds != self.refresh_period_active:
            self.publisher.publish_int(
                self.get_topic(mqtt_topics.REFRESH_PERIOD_ACTIVE), seconds
            )
            human_readable_period = str(datetime.timedelta(seconds=seconds))
            LOG.info(
                f"Setting active query interval in vehicle handler for VIN {self.vin} to {human_readable_period}"
            )
            self.refresh_period_active = seconds
            # Recompute charging refresh period, if active refresh period is changed
            self.set_refresh_period_charging(self.refresh_period_charging)

    def set_refresh_period_inactive(self, seconds: int) -> None:
        if seconds != self.refresh_period_inactive:
            self.publisher.publish_int(
                self.get_topic(mqtt_topics.REFRESH_PERIOD_INACTIVE), seconds
            )
            human_readable_period = str(datetime.timedelta(seconds=seconds))
            LOG.info(
                f"Setting inactive query interval in vehicle handler for VIN {self.vin} to {human_readable_period}"
            )
            self.refresh_period_inactive = seconds
            # Recompute charging refresh period, if inactive refresh period is changed
            self.set_refresh_period_charging(self.refresh_period_charging)

    def set_refresh_period_charging(self, seconds: float) -> None:
        # Do not refresh more than the active period and less than the inactive one
        seconds = round(seconds)
        seconds = (
            min(max(seconds, self.refresh_period_active), self.refresh_period_inactive)
            if seconds > 0
            else 0
        )
        if seconds != self.refresh_period_charging:
            self.publisher.publish_int(
                self.get_topic(mqtt_topics.REFRESH_PERIOD_CHARGING), seconds
            )
            human_readable_period = str(datetime.timedelta(seconds=seconds))
            LOG.info(
                f"Setting charging query interval in vehicle handler for VIN {self.vin} to {human_readable_period}"
            )
            self.refresh_period_charging = seconds

    def set_refresh_period_after_shutdown(self, seconds: int) -> None:
        if seconds != self.refresh_period_after_shutdown:
            self.publisher.publish_int(
                self.get_topic(mqtt_topics.REFRESH_PERIOD_AFTER_SHUTDOWN), seconds
            )
            human_readable_period = str(datetime.timedelta(seconds=seconds))
            LOG.info(
                f"Setting after shutdown query interval in vehicle handler for VIN {self.vin} to {human_readable_period}"
            )
            self.refresh_period_after_shutdown = seconds

    def set_refresh_period_inactive_grace(
        self, refresh_period_inactive_grace: int
    ) -> None:
        if (
            self.refresh_period_inactive_grace == -1
            or self.refresh_period_inactive_grace != refresh_period_inactive_grace
        ):
            self.publisher.publish_int(
                self.get_topic(mqtt_topics.REFRESH_PERIOD_INACTIVE_GRACE),
                refresh_period_inactive_grace,
            )
            self.refresh_period_inactive_grace = refresh_period_inactive_grace

    def update_target_soc(self, target_soc: TargetBatteryCode) -> None:
        if self.target_soc != target_soc and target_soc is not None:
            self.publisher.publish_int(
                self.get_topic(mqtt_topics.DRIVETRAIN_SOC_TARGET), target_soc.percentage
            )
            self.target_soc = target_soc

    def update_charge_current_limit(
        self, charge_current_limit: ChargeCurrentLimitCode
    ) -> None:
        if (
            self.charge_current_limit != charge_current_limit
            and charge_current_limit is not None
        ):
            try:
                self.publisher.publish_str(
                    self.get_topic(mqtt_topics.DRIVETRAIN_CHARGECURRENT_LIMIT),
                    charge_current_limit.limit,
                )
                self.charge_current_limit = charge_current_limit
            except ValueError:
                LOG.exception(f"Unhandled charge current limit {charge_current_limit}")

    def update_scheduled_charging(
        self, start_time: datetime.time, mode: ScheduledChargingMode
    ) -> None:
        scheduled_charging_job_id = f"{self.vin}_scheduled_charging"
        existing_job: Job | None = self.__scheduler.get_job(scheduled_charging_job_id)
        if mode in [
            ScheduledChargingMode.UNTIL_CONFIGURED_TIME,
            ScheduledChargingMode.UNTIL_CONFIGURED_SOC,
        ]:
            if self.refresh_period_inactive_grace > 0:
                # Add a grace period to the start time, so that the car is not woken up too early
                dt = datetime.datetime.now().replace(
                    hour=start_time.hour,
                    minute=start_time.minute,
                    second=0,
                    microsecond=0,
                ) + datetime.timedelta(seconds=self.refresh_period_inactive_grace)
                start_time = dt.time()
            trigger = CronTrigger.from_crontab(
                f"{start_time.minute} {start_time.hour} * * *"
            )
            if existing_job is not None:
                existing_job.reschedule(trigger=trigger)
                LOG.info(
                    f"Rescheduled check for charging start for VIN {self.vin} at {start_time}"
                )
            else:
                self.__scheduler.add_job(
                    func=self.set_refresh_mode,
                    args=[RefreshMode.FORCE, "check for scheduled charging start"],
                    trigger=trigger,
                    kwargs={},
                    name=scheduled_charging_job_id,
                    id=scheduled_charging_job_id,
                    replace_existing=True,
                )
                LOG.info(
                    f"Scheduled check for charging start for VIN {self.vin} at {start_time}"
                )
        elif existing_job is not None:
            existing_job.remove()
            LOG.info(f"Removed scheduled check for charging start for VIN {self.vin}")

    def is_complete(self) -> bool:
        return (
            self.refresh_period_active != -1
            and self.refresh_period_inactive != -1
            and self.refresh_period_after_shutdown != -1
            and self.refresh_period_inactive_grace != -1
            and self.refresh_mode is not None
        )

    def set_is_charging(self, is_charging: bool) -> None:
        self.is_charging = is_charging
        self.hv_battery_active = self.is_charging
        self.publisher.publish_bool(
            self.get_topic(mqtt_topics.DRIVETRAIN_CHARGING), self.is_charging
        )

    def handle_vehicle_status(
        self, vehicle_status: VehicleStatusResp
    ) -> VehicleStatusRespProcessingResult:
        processing_result = self.__vehicle_response_publisher.on_vehicle_status_resp(
            vehicle_status
        )
        self.hv_battery_active_from_car = processing_result.hv_battery_active_from_car
        self.__remote_ac_running = processing_result.remote_ac_running
        if processing_result.remote_heated_seats_front_left_level is not None:
            self.__remote_heated_seats_front_left_level = (
                processing_result.remote_heated_seats_front_left_level
            )
        if processing_result.remote_heated_seats_front_right_level is not None:
            self.__remote_heated_seats_front_right_level = (
                processing_result.remote_heated_seats_front_right_level
            )
        return processing_result

    def __publish_electric_range(self, raw_value: int | None) -> bool:
        published, electric_range = self.__transform_and_publish(
            topic=mqtt_topics.DRIVETRAIN_RANGE,
            value=raw_value,
            validator=lambda x: value_in_range(x, 1, 20460),
            transform=lambda x: x / 10.0,
        )
        if self.charging_station is not None and self.charging_station.range_topic:
            self.__publish(
                topic=self.charging_station.range_topic,
                value=electric_range,
                no_prefix=True,
            )
        return published

    def __publish_soc(self, soc: float | None) -> bool:
        published, published_soc = self.__transform_and_publish(
            topic=mqtt_topics.DRIVETRAIN_SOC,
            value=soc,
            validator=lambda v: value_in_range(v, 0, 100.0, is_max_excl=False),
            transform=lambda x: 1.0 * x,
        )
        if self.charging_station is not None and self.charging_station.soc_topic:
            self.__publish(
                topic=self.charging_station.soc_topic,
                value=published_soc,
                no_prefix=True,
            )
        return published

    @property
    def hv_battery_active(self) -> bool:
        return self.__hv_battery_active

    @hv_battery_active.setter
    def hv_battery_active(self, new_state: bool) -> None:
        self.__hv_battery_active = new_state
        self.__publish(
            topic=mqtt_topics.DRIVETRAIN_HV_BATTERY_ACTIVE,
            value=new_state,
        )
        if new_state:
            self.notify_car_activity()

    @property
    def hv_battery_active_from_car(self) -> bool:
        return self.__hv_battery_active_from_car

    @hv_battery_active_from_car.setter
    def hv_battery_active_from_car(self, new_state: bool) -> None:
        old_state = self.__hv_battery_active_from_car
        if old_state and not new_state:
            self.last_car_shutdown = datetime.datetime.now()
            LOG.info(
                f"Detected vehicle {self.vin} shutdown at {self.last_car_shutdown}"
            )
        self.__hv_battery_active_from_car = new_state

    def notify_car_activity(self) -> None:
        self.last_car_activity = datetime.datetime.now()
        self.__publish(
            topic=mqtt_topics.REFRESH_LAST_ACTIVITY,
            value=datetime_to_str(self.last_car_activity),
        )

    def notify_message(self, message: MessageEntity) -> None:
        result = self.__message_publisher.on_message(message)
        if result.processed:
            self.notify_car_activity()

    def should_refresh(self) -> bool:
        match self.refresh_mode:
            case RefreshMode.OFF:
                LOG.debug(f"Refresh mode is OFF, skipping vehicle {self.vin} refresh")
                return False
            case RefreshMode.FORCE:
                LOG.debug(f"Refresh mode is FORCE, skipping vehicle {self.vin} refresh")
                self.set_refresh_mode(
                    self.previous_refresh_mode,
                    "restoring of previous refresh mode after a FORCE execution",
                )
                return True
            # RefreshMode.PERIODIC is treated like default
            case other:
                LOG.debug(
                    f"Refresh mode is {other}, checking for other vehicle {self.vin} conditions"
                )
                last_actual_poll = self.last_successful_refresh
                if self.last_failed_refresh is not None:
                    last_actual_poll = max(last_actual_poll, self.last_failed_refresh)

                # Try refreshing even if we last failed as long as the last_car_activity is newer
                if self.last_car_activity > last_actual_poll:
                    LOG.debug(
                        f"Polling vehicle {self.vin} as last_car_activity is newer than last_actual_poll."
                        f" {self.last_car_activity} > {last_actual_poll}"
                    )
                    return True

                if self.last_failed_refresh is not None:
                    threshold = datetime.datetime.now() - datetime.timedelta(
                        seconds=float(self.refresh_period_error)
                    )
                    result: bool = self.last_failed_refresh < threshold
                    LOG.debug(
                        f"Gateway failed refresh previously. Should refresh: {result}"
                    )
                    return result

                if self.is_charging and self.refresh_period_charging > 0:
                    result = (
                        self.last_successful_refresh
                        < datetime.datetime.now()
                        - datetime.timedelta(
                            seconds=float(self.refresh_period_charging)
                        )
                    )
                    LOG.debug(f"HV battery is charging. Should refresh: {result}")
                    return result

                if self.hv_battery_active:
                    result = (
                        self.last_successful_refresh
                        < datetime.datetime.now()
                        - datetime.timedelta(seconds=float(self.refresh_period_active))
                    )
                    LOG.debug(f"HV battery is active. Should refresh: {result}")
                    return result

                last_shutdown_plus_refresh = (
                    self.last_car_shutdown
                    + datetime.timedelta(
                        seconds=float(self.refresh_period_inactive_grace)
                    )
                )
                if last_shutdown_plus_refresh > datetime.datetime.now():
                    result = (
                        self.last_successful_refresh
                        < datetime.datetime.now()
                        - datetime.timedelta(
                            seconds=float(self.refresh_period_after_shutdown)
                        )
                    )
                    LOG.debug(
                        f"Refresh grace period after shutdown has not passed. Should refresh: {result}"
                    )
                    return result

                result = (
                    self.last_successful_refresh
                    < datetime.datetime.now()
                    - datetime.timedelta(seconds=float(self.refresh_period_inactive))
                )
                LOG.debug(
                    f"HV battery is inactive and refresh period after shutdown is over. Should refresh: {result}"
                )
                return result

    def mark_successful_refresh(self) -> None:
        self.last_successful_refresh = datetime.datetime.now()
        self.last_failed_refresh = None
        self.publisher.publish_str(self.get_topic(mqtt_topics.AVAILABLE), "online")

    def mark_failed_refresh(self) -> None:
        self.last_failed_refresh = datetime.datetime.now()
        self.publisher.publish_str(self.get_topic(mqtt_topics.AVAILABLE), "offline")

    @property
    def refresh_period_error(self) -> int:
        return self.__refresh_period_error

    @property
    def last_failed_refresh(self) -> datetime.datetime | None:
        return self.__last_failed_refresh

    @last_failed_refresh.setter
    def last_failed_refresh(self, value: datetime.datetime | None) -> None:
        self.__last_failed_refresh = value
        if value is None:
            self.__failed_refresh_counter = 0
            self.__refresh_period_error = self.refresh_period_active
        elif self.__refresh_period_error < self.refresh_period_inactive:
            self.__refresh_period_error = round(
                min(
                    self.refresh_period_active * (2**self.__failed_refresh_counter),
                    self.refresh_period_inactive,
                )
            )
            self.__failed_refresh_counter = self.__failed_refresh_counter + 1
            self.publisher.publish_str(
                self.get_topic(mqtt_topics.REFRESH_LAST_ERROR), datetime_to_str(value)
            )
        self.publisher.publish_int(
            self.get_topic(mqtt_topics.REFRESH_PERIOD_ERROR),
            self.__refresh_period_error,
        )

    def configure_missing(self) -> None:
        if self.refresh_period_active == -1:
            self.set_refresh_period_active(30)
        if self.refresh_period_after_shutdown == -1:
            self.set_refresh_period_after_shutdown(120)
        if self.refresh_period_inactive == -1:
            # in seconds (Once a day to protect your 12V battery)
            self.set_refresh_period_inactive(86400)
        if self.refresh_period_inactive_grace == -1:
            self.set_refresh_period_inactive_grace(600)
        if self.__remote_ac_temp is None:
            self.set_ac_temperature(DEFAULT_AC_TEMP)
        # Make sure the only refresh mode that is not supported at start is RefreshMode.PERIODIC
        if self.refresh_mode in [RefreshMode.OFF, RefreshMode.FORCE]:
            self.set_refresh_mode(
                RefreshMode.PERIODIC,
                f"initial gateway startup from an invalid state {self.refresh_mode}",
            )

    async def configure_by_message(self, *, topic: str, payload: str) -> None:
        payload = payload.lower()
        match topic:
            case mqtt_topics.REFRESH_MODE_SET:
                try:
                    refresh_mode = RefreshMode.get(payload)
                    self.set_refresh_mode(
                        refresh_mode, "MQTT direct set refresh mode command execution"
                    )
                except KeyError as e:
                    msg = f"Unsupported payload {payload}"
                    raise MqttGatewayException(msg) from e
            case mqtt_topics.REFRESH_PERIOD_ACTIVE_SET:
                try:
                    seconds = int(payload)
                    self.set_refresh_period_active(seconds)
                except ValueError as e:
                    msg = f"Error setting value for payload {payload}"
                    raise MqttGatewayException(msg) from e
            case mqtt_topics.REFRESH_PERIOD_INACTIVE_SET:
                try:
                    seconds = int(payload)
                    self.set_refresh_period_inactive(seconds)
                except ValueError as e:
                    msg = f"Error setting value for paylo d {payload}"
                    raise MqttGatewayException(msg) from e
            case mqtt_topics.REFRESH_PERIOD_AFTER_SHUTDOWN_SET:
                try:
                    seconds = int(payload)
                    self.set_refresh_period_after_shutdown(seconds)
                except ValueError as e:
                    msg = f"Error setting value for payload {payload}"
                    raise MqttGatewayException(msg) from e
            case mqtt_topics.REFRESH_PERIOD_INACTIVE_GRACE_SET:
                try:
                    seconds = int(payload)
                    self.set_refresh_period_inactive_grace(seconds)
                except ValueError as e:
                    msg = f"Error setting value for payload {payload}"
                    raise MqttGatewayException(msg) from e
            case _:
                msg = f"Unsupported topic {topic}"
                raise MqttGatewayException(msg)

    def handle_charge_status(
        self, charge_info_resp: ChrgMgmtDataResp
    ) -> ChrgMgmtDataRespProcessingResult:
        result = self.__charge_response_publisher.on_chrg_mgmt_data_resp(
            charge_info_resp
        )

        if result.scheduled_charging is not None:
            self.update_scheduled_charging(
                result.scheduled_charging.start_time, result.scheduled_charging.mode
            )

        if result.charge_current_limit is not None:
            self.update_charge_current_limit(result.charge_current_limit)

        if result.target_soc is not None:
            self.update_target_soc(result.target_soc)

        # We are charging if the BMS tells us so
        self.is_charging = result.is_charging or False

        if self.is_charging and result.power is not None and result.power < -1:
            # Only compute a dynamic refresh period if we have detected at least 1kW of power during charging
            time_for_1pct = (
                36.0 * result.real_total_battery_capacity / abs(result.power)
            )
            time_for_min_pct = math.ceil(
                self.charge_polling_min_percent * time_for_1pct
            )
            # It doesn't make sense to refresh less often than the estimated time for completion
            if (
                result.remaining_charging_time is not None
                and result.remaining_charging_time > 0
            ):
                computed_refresh_period = float(
                    min(result.remaining_charging_time, time_for_min_pct)
                )
            else:
                computed_refresh_period = time_for_1pct
            self.set_refresh_period_charging(computed_refresh_period)
        elif not self.is_charging:
            # Reset the charging refresh period if we detected we are no longer charging
            self.set_refresh_period_charging(0)
        else:
            # Otherwise let's keep the last computed refresh period
            # This avoids falling back to the active refresh period which, being too often, results in a ban from
            # the SAIC API
            pass

        return result

    def update_data_conflicting_in_vehicle_and_bms(
        self,
        vehicle_status: VehicleStatusRespProcessingResult,
        charge_status: ChrgMgmtDataRespProcessingResult | None,
    ) -> None:
        # Deduce if the car is awake or not
        hv_battery_active = self.is_charging or self.hv_battery_active_from_car
        LOG.debug(
            f"Vehicle {self.vin} hv_battery_active={hv_battery_active}. "
            f"is_charging={self.is_charging} "
            f"hv_battery_active_from_car={self.hv_battery_active_from_car}"
        )
        self.hv_battery_active = hv_battery_active

        # We can read this from either the BMS or the Vehicle Info
        electric_range_published = False
        soc_published = False

        if charge_status is not None:
            if (raw_fuel_range_elec := charge_status.raw_fuel_range_elec) is not None:
                electric_range_published = self.__publish_electric_range(
                    raw_fuel_range_elec
                )

            if (soc := charge_status.raw_soc) is not None:
                soc_published = self.__publish_soc(soc / 10.0)

        if not electric_range_published:
            electric_range_published = self.__publish_electric_range(
                vehicle_status.fuel_range_elec
            )
        if not soc_published:
            soc_published = self.__publish_soc(vehicle_status.raw_soc)

        if not electric_range_published:
            LOG.warning("Could not extract a valid electric range")

        if not soc_published:
            LOG.warning("Could not extract a valid SoC")

    def handle_scheduled_battery_heating_status(
        self, scheduled_battery_heating_status: ScheduledBatteryHeatingResp | None
    ) -> None:
        if scheduled_battery_heating_status:
            is_enabled = scheduled_battery_heating_status.is_enabled
            if is_enabled:
                start_time = scheduled_battery_heating_status.decoded_start_time
            else:
                start_time = self.__scheduled_battery_heating_start
        else:
            start_time = self.__scheduled_battery_heating_start
            is_enabled = False

        self.update_scheduled_battery_heating(start_time, is_enabled)

    def update_scheduled_battery_heating(
        self, start_time: datetime.time | None, enabled: bool
    ) -> bool:
        changed = False
        if self.__scheduled_battery_heating_start != start_time:
            self.__scheduled_battery_heating_start = start_time
            changed = True
        if self.__scheduled_battery_heating_enabled != enabled:
            self.__scheduled_battery_heating_enabled = enabled
            changed = True

        computed_mode = (
            "on"
            if start_time is not None and self.__scheduled_battery_heating_enabled
            else "off"
        )
        computed_start_time = (
            start_time.strftime("%H:%M") if start_time is not None else "00:00"
        )
        self.publisher.publish_json(
            self.get_topic(mqtt_topics.DRIVETRAIN_BATTERY_HEATING_SCHEDULE),
            {"mode": computed_mode, "startTime": computed_start_time},
        )
        return changed

    def get_topic(self, sub_topic: str) -> str:
        return f"{self.mqtt_vin_prefix}/{sub_topic}"

    def set_refresh_mode(self, mode: RefreshMode, cause: str) -> None:
        if mode is not None and (
            self.refresh_mode is None or self.refresh_mode != mode
        ):
            new_mode_value = mode.value
            LOG.info("Setting refresh mode to %s due to %s", new_mode_value, cause)
            self.publisher.publish_str(
                self.get_topic(mqtt_topics.REFRESH_MODE), new_mode_value
            )
            # Make sure we never store FORCE as previous refresh mode
            if self.refresh_mode != RefreshMode.FORCE:
                self.previous_refresh_mode = self.refresh_mode
            self.refresh_mode = mode
            LOG.debug("Refresh mode set to %s due to %s", self.refresh_mode, cause)

    @property
    def is_heated_seats_running(self) -> bool:
        return (
            self.__remote_heated_seats_front_right_level
            + self.__remote_heated_seats_front_left_level
        ) > 0

    @property
    def remote_heated_seats_front_left_level(self) -> int:
        return self.__remote_heated_seats_front_left_level

    def update_heated_seats_front_left_level(self, level: int) -> bool:
        if not self.__check_heated_seats_level(level):
            return False
        changed = self.__remote_heated_seats_front_left_level != level
        self.__remote_heated_seats_front_left_level = level
        return changed

    @property
    def remote_heated_seats_front_right_level(self) -> int:
        return self.__remote_heated_seats_front_right_level

    def update_heated_seats_front_right_level(self, level: int) -> bool:
        if not self.__check_heated_seats_level(level):
            return False
        changed = self.__remote_heated_seats_front_right_level != level
        self.__remote_heated_seats_front_right_level = level
        return changed

    def __check_heated_seats_level(self, level: int) -> bool:
        if not self.vehicle.has_heated_seats:
            return False
        if self.vehicle.has_level_heated_seats and not (0 <= level <= 3):
            msg = f"Invalid heated seat level {level}. Range must be from 0 to 3 inclusive"
            raise ValueError(msg)
        if self.vehicle.has_on_off_heated_seats and not (0 <= level <= 1):
            msg = f"Invalid heated seat level {level}. Range must be from 0 to 1 inclusive"
            raise ValueError(msg)
        return True

    def get_remote_ac_temperature(self) -> int:
        return self.__remote_ac_temp or DEFAULT_AC_TEMP

    def set_ac_temperature(self, temp: int) -> bool:
        temp = max(
            self.vehicle.min_ac_temperature,
            min(self.vehicle.max_ac_temperature, temp),
        )
        if self.__remote_ac_temp != temp:
            self.__remote_ac_temp = temp
            LOG.info("Updating remote AC temperature to %d", temp)
            self.publisher.publish_int(
                self.get_topic(mqtt_topics.CLIMATE_REMOTE_TEMPERATURE), temp
            )
            return True
        return False

    def get_ac_temperature_idx(self) -> int:
        return self.vehicle.get_ac_temperature_idx(self.get_remote_ac_temperature())

    @property
    def is_remote_ac_running(self) -> bool:
        return self.__remote_ac_running

    def __publish(
        self,
        *,
        topic: str,
        value: Publishable | None,
        validator: Callable[[Publishable], bool] = lambda _: True,
        no_prefix: bool = False,
    ) -> tuple[bool, Publishable | None]:
        if value is None or not validator(value):
            return False, None
        actual_topic = topic if no_prefix else self.get_topic(topic)
        published = self.__publish_directly(topic=actual_topic, value=value)
        return published, value

    def __transform_and_publish(
        self,
        *,
        topic: str,
        value: T | None,
        validator: Callable[[T], bool] = lambda _: True,
        transform: Callable[[T], Publishable],
        no_prefix: bool = False,
    ) -> tuple[bool, Publishable | None]:
        if value is None or not validator(value):
            return False, None
        actual_topic = topic if no_prefix else self.get_topic(topic)
        transformed_value = transform(value)
        published = self.__publish_directly(topic=actual_topic, value=transformed_value)
        return published, transformed_value

    def __publish_directly(self, *, topic: str, value: Publishable) -> bool:
        published = False
        if isinstance(value, bool):
            self.publisher.publish_bool(topic, value)
            published = True
        elif isinstance(value, int):
            self.publisher.publish_int(topic, value)
            published = True
        elif isinstance(value, float):
            self.publisher.publish_float(topic, value)
            published = True
        elif isinstance(value, str):
            self.publisher.publish_str(topic, value)
            published = True
        elif isinstance(value, dict):
            self.publisher.publish_json(topic, value)
            published = True
        elif isinstance(value, datetime.datetime):
            self.publisher.publish_str(topic, datetime_to_str(value))
            published = True
        return published

    @property
    def vin(self) -> str:
        return self.vehicle.vin
