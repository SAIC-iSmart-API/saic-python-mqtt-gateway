from __future__ import annotations

import dataclasses
import datetime
import logging
import math

from saic_ismart_client_ng.api.vehicle_charging import (
    ChargeCurrentLimitCode,
    ChrgMgmtData,
    ScheduledChargingMode,
    TargetBatteryCode,
)

import mqtt_topics
from status_publisher import VehicleDataPublisher
from utils import int_to_bool, value_in_range

LOG = logging.getLogger(__name__)


@dataclasses.dataclass(kw_only=True, frozen=True)
class ScheduledCharging:
    start_time: datetime.time
    mode: ScheduledChargingMode


@dataclasses.dataclass(kw_only=True, frozen=True)
class ChrgMgmtDataProcessingResult:
    charge_current_limit: ChargeCurrentLimitCode | None
    target_soc: TargetBatteryCode | None
    scheduled_charging: ScheduledCharging | None
    is_charging: bool
    remaining_charging_time: int | None
    power: float | None
    raw_soc: int | None


class ChrgMgmtDataPublisher(VehicleDataPublisher):
    def on_chrg_mgmt_data(
        self, charge_mgmt_data: ChrgMgmtData
    ) -> ChrgMgmtDataProcessingResult:
        is_valid_raw_current = (
            charge_mgmt_data.bmsPackCrntV != 1
            and charge_mgmt_data.bmsPackCrnt is not None
            and value_in_range(charge_mgmt_data.bmsPackCrnt, 0, 65535)
            and charge_mgmt_data.decoded_current is not None
        )
        is_valid_current, _ = self._transform_and_publish(
            topic=mqtt_topics.DRIVETRAIN_CURRENT,
            value=charge_mgmt_data.decoded_current,
            validator=lambda _: is_valid_raw_current,
            transform=lambda x: round(x, 3),
        )

        is_valid_raw_voltage = (
            charge_mgmt_data.bmsPackVol is not None
            and value_in_range(charge_mgmt_data.bmsPackVol, 0, 65535)
        )
        is_valid_voltage, _ = self._transform_and_publish(
            topic=mqtt_topics.DRIVETRAIN_VOLTAGE,
            value=charge_mgmt_data.decoded_voltage,
            validator=lambda _: is_valid_raw_voltage,
            transform=lambda x: round(x, 3),
        )

        is_valid_power, _ = self._transform_and_publish(
            topic=mqtt_topics.DRIVETRAIN_POWER,
            value=charge_mgmt_data.decoded_power,
            validator=lambda _: is_valid_current and is_valid_voltage,
            transform=lambda x: round(x, 3),
        )

        obc_voltage = charge_mgmt_data.onBdChrgrAltrCrntInptVol
        obc_current = charge_mgmt_data.onBdChrgrAltrCrntInptCrnt
        if obc_voltage is not None and obc_current is not None:
            self._publish(
                topic=mqtt_topics.OBC_CURRENT,
                value=round(obc_current / 5.0, 1),
            )
            self._publish(
                topic=mqtt_topics.OBC_VOLTAGE,
                value=2 * obc_voltage,
            )
            self._publish(
                topic=mqtt_topics.OBC_POWER_SINGLE_PHASE,
                value=round(2.0 * obc_voltage * obc_current / 5.0, 1),
            )
            self._publish(
                topic=mqtt_topics.OBC_POWER_THREE_PHASE,
                value=round(math.sqrt(3) * 2 * obc_voltage * obc_current / 15.0, 1),
            )
        else:
            self._publish(
                topic=mqtt_topics.OBC_CURRENT,
                value=0.0,
            )
            self._publish(
                topic=mqtt_topics.OBC_VOLTAGE,
                value=0,
            )

        raw_charge_current_limit = charge_mgmt_data.bmsAltngChrgCrntDspCmd
        charge_current_limit: ChargeCurrentLimitCode | None = None
        if raw_charge_current_limit is not None and raw_charge_current_limit != 0:
            try:
                charge_current_limit = ChargeCurrentLimitCode(raw_charge_current_limit)
            except ValueError:
                LOG.warning(
                    f"Invalid charge current limit received: {raw_charge_current_limit}"
                )

        raw_target_soc = charge_mgmt_data.bmsOnBdChrgTrgtSOCDspCmd
        target_soc: TargetBatteryCode | None = None
        if raw_target_soc is not None:
            try:
                target_soc = TargetBatteryCode(raw_target_soc)
            except ValueError:
                LOG.warning(f"Invalid target SOC received: {raw_target_soc}")

        self._publish(
            topic=mqtt_topics.DRIVETRAIN_HYBRID_ELECTRICAL_RANGE,
            value=charge_mgmt_data.bmsEstdElecRng,
            validator=lambda x: value_in_range(x, 0, 2046),
        )

        self._transform_and_publish(
            topic=mqtt_topics.BMS_CHARGE_STATUS,
            value=charge_mgmt_data.bms_charging_status,
            transform=lambda x: f"UNKNOWN {charge_mgmt_data.bmsChrgSts}"
            if x is None
            else x.name,
        )

        self._transform_and_publish(
            topic=mqtt_topics.DRIVETRAIN_CHARGING_STOP_REASON,
            value=charge_mgmt_data.charging_stop_reason,
            transform=lambda x: f"UNKNOWN {charge_mgmt_data.bmsChrgSpRsn}"
            if x is None
            else x.name,
        )

        self._publish(
            topic=mqtt_topics.CCU_ONBOARD_PLUG_STATUS,
            value=charge_mgmt_data.ccuOnbdChrgrPlugOn,
        )

        self._publish(
            topic=mqtt_topics.CCU_OFFBOARD_PLUG_STATUS,
            value=charge_mgmt_data.ccuOffBdChrgrPlugOn,
        )

        scheduled_charging: ScheduledCharging | None = None
        if charge_mgmt_data is not None and (
            charge_mgmt_data.bmsReserStHourDspCmd is not None
            and charge_mgmt_data.bmsReserStMintueDspCmd is not None
            and charge_mgmt_data.bmsReserSpHourDspCmd is not None
            and charge_mgmt_data.bmsReserSpMintueDspCmd is not None
        ):
            try:
                start_hour = charge_mgmt_data.bmsReserStHourDspCmd
                start_minute = charge_mgmt_data.bmsReserStMintueDspCmd
                start_time = datetime.time(hour=start_hour, minute=start_minute)
                end_hour = charge_mgmt_data.bmsReserSpHourDspCmd
                end_minute = charge_mgmt_data.bmsReserSpMintueDspCmd
                mode = ScheduledChargingMode(charge_mgmt_data.bmsReserCtrlDspCmd)
                self._publish(
                    topic=mqtt_topics.DRIVETRAIN_CHARGING_SCHEDULE,
                    value={
                        "startTime": f"{start_hour:02d}:{start_minute:02d}",
                        "endTime": f"{end_hour:02d}:{end_minute:02d}",
                        "mode": mode.name,
                    },
                )
                scheduled_charging = ScheduledCharging(start_time=start_time, mode=mode)

            except ValueError:
                LOG.exception("Error parsing scheduled charging info")

        # Only publish remaining charging time if the car tells us the value is OK
        remaining_charging_time: int | None = None
        valid_remaining_time, remaining_charging_time = self._transform_and_publish(
            topic=mqtt_topics.DRIVETRAIN_REMAINING_CHARGING_TIME,
            value=charge_mgmt_data.chrgngRmnngTime,
            validator=lambda _: charge_mgmt_data.chrgngRmnngTimeV != 1,
            transform=lambda x: x * 60,
        )
        if not valid_remaining_time:
            self._publish(topic=mqtt_topics.DRIVETRAIN_REMAINING_CHARGING_TIME, value=0)

        # We are charging if the BMS tells us so
        is_charging = charge_mgmt_data.is_bms_charging
        self._publish(topic=mqtt_topics.DRIVETRAIN_CHARGING, value=is_charging)

        self._publish(
            topic=mqtt_topics.DRIVETRAIN_BATTERY_HEATING,
            value=charge_mgmt_data.is_battery_heating,
        )

        self._transform_and_publish(
            topic=mqtt_topics.DRIVETRAIN_BATTERY_HEATING_STOP_REASON,
            value=charge_mgmt_data.heating_stop_reason,
            transform=lambda x: f"UNKNOWN ({charge_mgmt_data.bmsPTCHeatResp})"
            if x is None
            else x.name,
        )

        self._transform_and_publish(
            topic=mqtt_topics.DRIVETRAIN_CHARGING_CABLE_LOCK,
            value=charge_mgmt_data.charging_port_locked,
            transform=int_to_bool,
        )

        return ChrgMgmtDataProcessingResult(
            charge_current_limit=charge_current_limit,
            target_soc=target_soc,
            scheduled_charging=scheduled_charging,
            is_charging=is_charging,
            remaining_charging_time=remaining_charging_time,
            power=charge_mgmt_data.decoded_power if is_valid_power else None,
            raw_soc=charge_mgmt_data.bmsPackSOCDsp,
        )
