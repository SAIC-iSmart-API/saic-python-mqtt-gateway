from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

import mqtt_topics
from status_publisher import VehicleDataPublisher
from utils import int_to_bool, value_in_range

if TYPE_CHECKING:
    from saic_ismart_client_ng.api.vehicle_charging import RvsChargeStatus

LOG = logging.getLogger(__name__)


@dataclass(kw_only=True, frozen=True)
class RvsChargeStatusProcessingResult:
    real_total_battery_capacity: float
    raw_fuel_range_elec: int | None


class RvsChargeStatusPublisher(VehicleDataPublisher):
    def on_rvs_charge_status(
        self, charge_status: RvsChargeStatus
    ) -> RvsChargeStatusProcessingResult:
        self._transform_and_publish(
            topic=mqtt_topics.DRIVETRAIN_MILEAGE_OF_DAY,
            value=charge_status.mileageOfDay,
            validator=lambda x: value_in_range(x, 0, 65535),
            transform=lambda x: x / 10.0,
        )

        self._transform_and_publish(
            topic=mqtt_topics.DRIVETRAIN_MILEAGE_SINCE_LAST_CHARGE,
            value=charge_status.mileageSinceLastCharge,
            validator=lambda x: value_in_range(x, 0, 65535),
            transform=lambda x: x / 10.0,
        )

        self._publish(
            topic=mqtt_topics.DRIVETRAIN_CHARGING_TYPE,
            value=charge_status.chargingType,
        )

        self._transform_and_publish(
            topic=mqtt_topics.DRIVETRAIN_CHARGER_CONNECTED,
            value=charge_status.chargingGunState,
            transform=int_to_bool,
        )

        self._publish(
            topic=mqtt_topics.DRIVETRAIN_CHARGING_LAST_START,
            value=charge_status.startTime,
            validator=lambda x: value_in_range(x, 1, 2147483647),
        )

        self._publish(
            topic=mqtt_topics.DRIVETRAIN_CHARGING_LAST_END,
            value=charge_status.endTime,
            validator=lambda x: value_in_range(x, 1, 2147483647),
        )

        real_total_battery_capacity, battery_capacity_correction_factor = (
            self.get_actual_battery_capacity(charge_status)
        )

        self._publish(
            topic=mqtt_topics.DRIVETRAIN_TOTAL_BATTERY_CAPACITY,
            value=real_total_battery_capacity,
            validator=lambda x: x > 0,
        )

        self._transform_and_publish(
            topic=mqtt_topics.DRIVETRAIN_SOC_KWH,
            value=charge_status.realtimePower,
            transform=lambda p: round(
                (battery_capacity_correction_factor * p) / 10.0, 2
            ),
        )

        self._transform_and_publish(
            topic=mqtt_topics.DRIVETRAIN_LAST_CHARGE_ENDING_POWER,
            value=charge_status.lastChargeEndingPower,
            validator=lambda x: value_in_range(x, 0, 65535),
            transform=lambda p: round(
                (battery_capacity_correction_factor * p) / 10.0, 2
            ),
        )

        self._transform_and_publish(
            topic=mqtt_topics.DRIVETRAIN_POWER_USAGE_OF_DAY,
            value=charge_status.powerUsageOfDay,
            validator=lambda x: value_in_range(x, 0, 65535),
            transform=lambda p: round(
                (battery_capacity_correction_factor * p) / 10.0, 2
            ),
        )

        self._transform_and_publish(
            topic=mqtt_topics.DRIVETRAIN_POWER_USAGE_SINCE_LAST_CHARGE,
            value=charge_status.powerUsageSinceLastCharge,
            validator=lambda x: value_in_range(x, 0, 65535),
            transform=lambda p: round(
                (battery_capacity_correction_factor * p) / 10.0, 2
            ),
        )

        return RvsChargeStatusProcessingResult(
            real_total_battery_capacity=real_total_battery_capacity,
            raw_fuel_range_elec=charge_status.fuelRangeElec,
        )

    def get_actual_battery_capacity(
        self, charge_status: RvsChargeStatus
    ) -> tuple[float, float]:
        real_battery_capacity = self._vehicle_info.real_battery_capacity
        if real_battery_capacity is not None and real_battery_capacity <= 0:
            # Negative or 0 value for real capacity means we don't know that info
            real_battery_capacity = None

        raw_battery_capacity = None
        if (
            charge_status.totalBatteryCapacity is not None
            and charge_status.totalBatteryCapacity > 0
        ):
            raw_battery_capacity = charge_status.totalBatteryCapacity / 10.0

        if raw_battery_capacity is not None:
            if real_battery_capacity is not None:
                LOG.debug(
                    "Calculating full battery capacity correction factor based on "
                    "real=%f and raw=%f",
                    real_battery_capacity,
                    raw_battery_capacity,
                )
                return (
                    real_battery_capacity,
                    real_battery_capacity / raw_battery_capacity,
                )
            LOG.debug(
                "Setting real battery capacity to raw battery capacity %f",
                raw_battery_capacity,
            )
            return raw_battery_capacity, 1.0
        if real_battery_capacity is not None:
            LOG.debug(
                "Setting raw battery capacity to real battery capacity %f",
                real_battery_capacity,
            )
            return real_battery_capacity, 1.0
        LOG.warning("No battery capacity information available")
        return 0, 1.0
