from __future__ import annotations

from saic_ismart_client_ng.api.vehicle.schema import VehicleModelConfiguration, VinInfo

from tests.common_mocks import VIN
from vehicle_info import VehicleInfo


def _make_vehicle_info(
    series: str,
    model: str = "",
    btype: str | None = None,
    custom_battery_capacity: float | None = None,
) -> VehicleInfo:
    vin_info = VinInfo()
    vin_info.vin = VIN
    vin_info.series = series
    vin_info.modelName = model
    if btype is not None:
        vin_info.vehicleModelConfiguration = [
            VehicleModelConfiguration("BType", "Battery", btype),
        ]
    return VehicleInfo(vin_info, custom_battery_capacity)


class TestMg4RealBatteryCapacity:
    def test_mg4_lfp_51kwh(self) -> None:
        assert _make_vehicle_info("EH32 S", btype=None).real_battery_capacity == 51.0

    def test_mg4_nmc_64kwh(self) -> None:
        assert _make_vehicle_info("EH32 S", btype="1").real_battery_capacity == 64.0

    def test_mg4_trophy_extended_range_77kwh(self) -> None:
        assert (
            _make_vehicle_info("EH32 S", model="EH32 X3").real_battery_capacity == 77.0
        )


class TestMg4UrbanRealBatteryCapacity:
    def test_standard_range_43kwh(self) -> None:
        assert (
            _make_vehicle_info("AH4EM L", model="MG4 EV URBAN").real_battery_capacity
            == 43.0
        )

    def test_long_range_54kwh(self) -> None:
        # AH4EM S = Long Range (54kWh LFP), confirmed via issue #452
        assert (
            _make_vehicle_info("AH4EM S", model="MG4 EV URBAN").real_battery_capacity
            == 54.0
        )

    def test_custom_capacity_overrides_lookup(self) -> None:
        vi = _make_vehicle_info(
            "AH4EM L", model="MG4 EV URBAN", custom_battery_capacity=54.0
        )
        assert vi.real_battery_capacity == 54.0


class TestPowerTailgate:
    @staticmethod
    def _info(series: str, ctrl_boot: str | None = None) -> VehicleInfo:
        vin_info = VinInfo()
        vin_info.vin = VIN
        vin_info.series = series
        vin_info.modelName = "x"
        vin_info.modelYear = "2025"
        if ctrl_boot is not None:
            vin_info.vehicleModelConfiguration = [
                VehicleModelConfiguration("CTRLBOOT", "CTRLBOOT", ctrl_boot)
            ]
        return VehicleInfo(vin_info, None)

    def test_mg_s6_has_power_tailgate(self) -> None:
        assert self._info("MIS3E S").has_power_tailgate

    def test_other_series_has_no_power_tailgate(self) -> None:
        assert not self._info("EH32 S").has_power_tailgate

    def test_mg_s6_long_variant_has_no_power_tailgate(self) -> None:
        assert not self._info("MIS3E L").has_power_tailgate

    def test_ctrlboot_zero_removes_power_tailgate(self) -> None:
        assert not self._info("EH32 S", "0").has_power_tailgate
        assert not self._info("MIS3E S", "0").has_power_tailgate

    def test_ctrlboot_two_adds_power_tailgate(self) -> None:
        assert self._info("EH32 S", "2").has_power_tailgate
        assert self._info("MIS3E L", "2").has_power_tailgate

    def test_ctrlboot_one_falls_back_to_series(self) -> None:
        assert not self._info("EH32 S", "1").has_power_tailgate
        assert self._info("MIS3E S", "1").has_power_tailgate
