from __future__ import annotations

import dataclasses
import datetime
from typing import TYPE_CHECKING

import mqtt_topics
from status_publisher import VehicleDataPublisher
from status_publisher.charge.chrg_mgmt_data import (
    ChrgMgmtDataProcessingResult,
    ChrgMgmtDataPublisher,
    ScheduledCharging,
)
from status_publisher.charge.rvs_charge_status import (
    RvsChargeStatusProcessingResult,
    RvsChargeStatusPublisher,
)

if TYPE_CHECKING:
    from saic_ismart_client_ng.api.vehicle_charging import (
        ChargeCurrentLimitCode,
        ChrgMgmtDataResp,
        TargetBatteryCode,
    )

    from publisher.core import Publisher
    from vehicle_info import VehicleInfo


@dataclasses.dataclass(kw_only=True, frozen=True)
class ChrgMgmtDataRespProcessingResult:
    charge_current_limit: ChargeCurrentLimitCode | None
    target_soc: TargetBatteryCode | None
    scheduled_charging: ScheduledCharging | None
    is_charging: bool | None
    remaining_charging_time: int | None
    power: float | None
    real_total_battery_capacity: float
    raw_soc: int | None
    raw_fuel_range_elec: int | None


class ChrgMgmtDataRespPublisher(VehicleDataPublisher):
    def __init__(
        self, vin: VehicleInfo, publisher: Publisher, mqtt_vehicle_prefix: str
    ) -> None:
        super().__init__(vin, publisher, mqtt_vehicle_prefix)
        self.__chrg_mgmt_data_publisher = ChrgMgmtDataPublisher(
            vin, publisher, mqtt_vehicle_prefix
        )
        self.__rvs_charge_status_publisher = RvsChargeStatusPublisher(
            vin, publisher, mqtt_vehicle_prefix
        )

    def on_chrg_mgmt_data_resp(
        self, chrg_mgmt_data_resp: ChrgMgmtDataResp
    ) -> ChrgMgmtDataRespProcessingResult:
        chrg_mgmt_data = chrg_mgmt_data_resp.chrgMgmtData
        chrg_mgmt_data_result: ChrgMgmtDataProcessingResult | None = None
        if chrg_mgmt_data is not None:
            chrg_mgmt_data_result = self.__chrg_mgmt_data_publisher.on_chrg_mgmt_data(
                chrg_mgmt_data
            )

        charge_status = chrg_mgmt_data_resp.rvsChargeStatus
        charge_status_result: RvsChargeStatusProcessingResult | None = None
        if charge_status is not None:
            charge_status_result = (
                self.__rvs_charge_status_publisher.on_rvs_charge_status(charge_status)
            )
        else:
            pass

        if chrg_mgmt_data_result is not None or charge_status_result is not None:
            self._publish(
                topic=mqtt_topics.REFRESH_LAST_CHARGE_STATE,
                value=datetime.datetime.now(),
            )
        return ChrgMgmtDataRespProcessingResult(
            charge_current_limit=chrg_mgmt_data_result.charge_current_limit
            if chrg_mgmt_data_result is not None
            else None,
            target_soc=chrg_mgmt_data_result.target_soc
            if chrg_mgmt_data_result is not None
            else None,
            scheduled_charging=chrg_mgmt_data_result.scheduled_charging
            if chrg_mgmt_data_result is not None
            else None,
            is_charging=chrg_mgmt_data_result.is_charging
            if chrg_mgmt_data_result is not None
            else None,
            remaining_charging_time=chrg_mgmt_data_result.remaining_charging_time
            if chrg_mgmt_data_result is not None
            else None,
            power=chrg_mgmt_data_result.power
            if chrg_mgmt_data_result is not None
            else None,
            real_total_battery_capacity=charge_status_result.real_total_battery_capacity
            if charge_status_result is not None
            else 0.0,
            raw_soc=chrg_mgmt_data_result.raw_soc
            if chrg_mgmt_data_result is not None
            else None,
            raw_fuel_range_elec=charge_status_result.raw_fuel_range_elec
            if charge_status_result is not None
            else None,
        )
