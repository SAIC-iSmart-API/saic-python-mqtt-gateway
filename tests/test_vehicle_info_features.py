from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from saic_ismart_client_ng.api.vehicle.schema import (
    VehicleModelConfiguration,
    VinInfo,
)

from vehicle_info import VehicleInfo

from .common_mocks import VIN

# Real configurations shared by users in public issue reports
REAL_CONFIGURATIONS: list[dict[str, Any]] = json.loads(
    (
        Path(__file__).parent / "fixtures" / "vehicle_model_configurations.json"
    ).read_text()
)


def _vehicle_info(**codes: str) -> VehicleInfo:
    vin_info = VinInfo()
    vin_info.vin = VIN
    vin_info.vehicleModelConfiguration = [
        VehicleModelConfiguration(itemCode=code, itemName=code, itemValue=value)
        for code, value in codes.items()
    ]
    return VehicleInfo(vin_info, None)


def _real_vehicle_info(fixture: dict[str, Any]) -> VehicleInfo:
    vin_info = VinInfo()
    vin_info.vin = VIN
    vin_info.series = fixture["series"]
    vin_info.modelName = fixture["model"]
    vin_info.vehicleModelConfiguration = [
        VehicleModelConfiguration(**item) for item in fixture["configuration"]
    ]
    return VehicleInfo(vin_info, None)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("0", False), ("1", True), ("2", False), ("3", True), ("X", False)],
)
def test_has_sunroof(value: str, expected: bool) -> None:
    assert _vehicle_info(S35=value).has_sunroof is expected


def test_absent_codes_disable_features() -> None:
    vehicle_info = _vehicle_info()
    assert not vehicle_info.has_sunroof
    assert not vehicle_info.has_driver_door
    assert not vehicle_info.has_boot_status
    assert not vehicle_info.has_tyre_pressure
    assert not vehicle_info.has_interior_temperature


def test_door_mask_is_positional() -> None:
    vehicle_info = _vehicle_info(DOOR="1100")
    assert vehicle_info.has_driver_door
    assert vehicle_info.has_passenger_door
    assert not vehicle_info.has_rear_left_door
    assert not vehicle_info.has_rear_right_door


@pytest.mark.parametrize("mask", ["1", "111", "11111", ""])
def test_door_mask_with_wrong_length_disables_all(mask: str) -> None:
    vehicle_info = _vehicle_info(DOOR=mask)
    assert not vehicle_info.has_driver_door
    assert not vehicle_info.has_rear_right_door


@pytest.mark.parametrize(
    "fixture",
    REAL_CONFIGURATIONS,
    ids=[f"{c['model']}-{c['source'].rsplit('/', 1)[-1]}" for c in REAL_CONFIGURATIONS],
)
def test_real_configurations(fixture: dict[str, Any]) -> None:
    vehicle_info = _real_vehicle_info(fixture)
    is_two_door = fixture["series"] == "EC32"  # MG Cyberster
    assert vehicle_info.has_driver_door
    assert vehicle_info.has_passenger_door
    assert vehicle_info.has_rear_left_door is not is_two_door
    assert vehicle_info.has_rear_right_door is not is_two_door
    assert vehicle_info.has_boot_status
    assert vehicle_info.has_tyre_pressure
    assert vehicle_info.has_interior_temperature


def test_real_configurations_sunroof() -> None:
    with_sunroof = {
        c["source"] for c in REAL_CONFIGURATIONS if _real_vehicle_info(c).has_sunroof
    }
    assert with_sunroof == {
        "https://github.com/townsmcp/mg-saic-ha/issues/100",  # ZS EV, S35=3
        "https://github.com/townsmcp/mg-saic-ha/issues/98",  # ZS EV, S35=3
        "https://github.com/townsmcp/mg-saic-ha/issues/204",  # MG S9 PHEV, S35=3
    }
