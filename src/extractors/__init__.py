from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from utils import value_in_range

if TYPE_CHECKING:
    from status_publisher.charge.chrg_mgmt_data_resp import (
        ChrgMgmtDataRespProcessingResult,
    )
    from status_publisher.vehicle.vehicle_status_resp import (
        VehicleStatusRespProcessingResult,
    )

LOG = logging.getLogger(__name__)


def extract_electric_range(
    vehicle_status: VehicleStatusRespProcessingResult,
    charge_status: ChrgMgmtDataRespProcessingResult | None,
) -> float | None:
    if (
        charge_status is not None
        and (raw_fuel_range_elec := charge_status.raw_fuel_range_elec) is not None
        and (actual_range := __validate_and_convert_electric_range(raw_fuel_range_elec))
        is not None
    ):
        LOG.debug("Electric range derived from charge_status")
        return actual_range

    if (raw_range := vehicle_status.fuel_range_elec) is not None and (
        actual_range := __validate_and_convert_electric_range(raw_range)
    ) is not None:
        LOG.debug("Electric range derived from vehicle_status")
        return actual_range

    LOG.warning("Could not extract a valid electric range")
    return None


def extract_soc_kwh(
    charge_status: ChrgMgmtDataRespProcessingResult | None,
    soc: float | None,
) -> float | None:
    if charge_status is None:
        return None

    if (raw_soc_kwh := charge_status.soc_kwh) is not None and (
        soc_kwh := __validate_and_convert_soc_kwh(raw_soc_kwh)
    ) is not None:
        LOG.debug("SoC kWh derived from realtimePower")
        return soc_kwh

    if (
        soc is not None
        and (
            capacity := __validate_and_convert_soc_kwh(
                charge_status.real_total_battery_capacity
            )
        )
        is not None
    ):
        LOG.debug(
            "SoC kWh computed from SoC%%=%s and capacity=%s kWh",
            soc,
            capacity,
        )
        return round(soc / 100.0 * capacity, 2)

    LOG.warning("Could not extract a valid SoC kWh")
    return None


def extract_soc(
    vehicle_status: VehicleStatusRespProcessingResult,
    charge_status: ChrgMgmtDataRespProcessingResult | None,
) -> float | None:
    if (
        charge_status is not None
        and (raw_soc := charge_status.raw_soc) is not None
        and (soc := __validate_and_convert_soc(raw_soc / 10.0)) is not None
    ):
        LOG.debug("SoC derived from charge_status")
        return soc

    if (raw_soc := vehicle_status.raw_soc) is not None and (
        soc := __validate_and_convert_soc(float(raw_soc))
    ) is not None:
        LOG.debug("SoC derived from vehicle_status")
        return soc

    LOG.warning("Could not extract a valid SoC")
    return None


def __validate_and_convert_electric_range(raw_value: int) -> float | None:
    if value_in_range(raw_value, 1, 20460):
        return raw_value / 10.0
    return None


def __validate_and_convert_soc(raw_value: float) -> float | None:
    if value_in_range(raw_value, 0, 100.0, is_max_excl=False):
        return raw_value
    return None


def __validate_and_convert_soc_kwh(raw_value: float) -> float | None:
    if raw_value > 0:
        return raw_value
    return None
