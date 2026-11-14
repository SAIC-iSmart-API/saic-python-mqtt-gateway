from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

from exceptions import MqttGatewayException

if TYPE_CHECKING:
    from saic_ismart_client_ng.api.vehicle import VehicleModelConfiguration, VinInfo

LOG = logging.getLogger(__name__)


class VehicleInfo:
    def __init__(
        self,
        vin_info: VinInfo,
        custom_battery_capacity: float | None,
    ) -> None:
        if not vin_info.vin:
            raise MqttGatewayException("Could not handle a car without a vin")
        self.vin: Final[str] = vin_info.vin
        self.configuration: Final[list[VehicleModelConfiguration]] = (
            vin_info.vehicleModelConfiguration or []
        )
        self.brand: Final[str] = str(vin_info.brandName or "").strip()
        self.model: Final[str] = str(vin_info.modelName or "").strip().upper()
        self.model_year: Final[str] = str(vin_info.modelYear or "").strip()
        self.series: Final[str] = str(vin_info.series or "").strip().upper()
        self.color: Final[str] = str(vin_info.colorName or "").strip()
        self.__properties_by_code: Final[dict[str, str | None]] = (
            self.__properties_from_configuration(self.configuration)
        )
        self.__custom_battery_capacity: float | None = custom_battery_capacity
        self.__urban_capacity_hint_logged = False

    @property
    def custom_battery_capacity(self) -> float | None:
        return self.__custom_battery_capacity

    @custom_battery_capacity.setter
    def custom_battery_capacity(self, value: float) -> None:
        self.__custom_battery_capacity = value

    @staticmethod
    def __properties_from_configuration(
        configuration: list[VehicleModelConfiguration],
    ) -> dict[str, str | None]:
        properties: dict[str, str | None] = {}
        for c in configuration:
            if (code := c.itemCode) is not None:
                normalized_code = str(code).strip().upper()
                if (value := c.itemValue) is not None:
                    properties[normalized_code] = str(value).strip().upper()
                else:
                    properties[normalized_code] = None
        return properties

    def get_ac_temperature_idx(self, remote_ac_temperature: int) -> int:
        # The app sends temperature - 14. The offset below matches that for the
        # minimum temperature of each series.
        if self.series.startswith(("EH32", "ZS32")):
            return 3 + remote_ac_temperature - self.min_ac_temperature
        return 2 + remote_ac_temperature - self.min_ac_temperature

    @property
    def min_ac_temperature(self) -> int:
        if self.series.startswith(("EH32", "ZS32")):
            return 17
        return 16

    @property
    def max_ac_temperature(self) -> int:
        if self.series.startswith("ZS32"):
            # The app caps this series at 31 or 33 depending on its region. The car
            # panel of the reported ZS Hybrid+ goes up to 32 and then "HI".
            return 33
        if self.series.startswith(("EH32", "MZS3E")):
            return 31
        return 28

    def __get_property_by_code(self, property_name: str) -> str | None:
        normalized_property_name = str(property_name).strip().upper()
        return self.__properties_by_code.get(normalized_property_name)

    def __get_int_property_by_code(self, property_name: str) -> int | None:
        # None means the code is absent or not numeric, i.e. unknown
        try:
            return int(self.__get_property_by_code(property_name) or "")
        except ValueError:
            return None

    def __is_feature_enabled(self, property_name: str) -> bool:
        # Only a code that is present and 0 means "not available". An unknown
        # code keeps the feature: some vehicles omit codes but send the data.
        value = self.__get_int_property_by_code(property_name)
        return value is None or value != 0

    def __get_mask_by_code(self, property_name: str, index: int) -> bool:
        # 4-char positional mask: driver, passenger, rear left, rear right.
        # A missing or malformed mask is unknown and keeps the feature.
        mask = self.__get_property_by_code(property_name) or ""
        if len(mask) != 4 or set(mask) - {"0", "1"}:
            return True
        return mask[index] == "1"

    @property
    def is_ev(self) -> bool:
        # Hybrids without a plug: the charge management data is not available
        return not self.series.startswith(("ZP22", "ZS32"))

    @property
    def has_fossil_fuel(self) -> bool:
        return not self.is_ev

    @property
    def has_sunroof(self) -> bool:
        # The value 2 alone does not denote a sunroof
        value = self.__get_int_property_by_code("S35")
        return value is None or value & ~2 != 0

    @property
    def has_driver_door(self) -> bool:
        return self.__get_mask_by_code("DOOR", 0)

    @property
    def has_passenger_door(self) -> bool:
        return self.__get_mask_by_code("DOOR", 1)

    @property
    def has_rear_left_door(self) -> bool:
        return self.__get_mask_by_code("DOOR", 2)

    @property
    def has_rear_right_door(self) -> bool:
        return self.__get_mask_by_code("DOOR", 3)

    # WINDOW, BONNUT, BATTERY and EXTEMP are deliberately not used: real vehicles
    # report 0 for them while still sending the data (e.g. WINDOW=0000 on the MG4)

    @property
    def has_boot_status(self) -> bool:
        return self.__is_feature_enabled("BOOT")

    @property
    def has_tyre_pressure(self) -> bool:
        return self.__is_feature_enabled("J17")

    @property
    def has_interior_temperature(self) -> bool:
        return self.__is_feature_enabled("INTEMP")

    @property
    def has_power_tailgate(self) -> bool:
        # Mirrors the iSmart app: CTRLBOOT=2 adds the power tailgate, CTRLBOOT=0
        # removes it, and when the code is absent the car's series decides.
        ctrl_boot = self.__get_property_by_code("CTRLBOOT")
        if ctrl_boot is not None:
            value = ctrl_boot.strip()
            if value == "2":
                return True
            if value == "0":
                return False
        # Only the MG S6 EV (MIS3E) has one by default, not its long variant.
        # The app strips " S" and treats any remaining "L" as the long variant.
        normalized = self.series.replace(" S", "")
        return "MIS3E" in normalized and "L" not in normalized

    @property
    def has_on_off_heated_seats(self) -> bool:
        return self.__get_property_by_code("HeatedSeat") == "2"

    @property
    def has_level_heated_seats(self) -> bool:
        return self.__get_property_by_code("HeatedSeat") == "1"

    @property
    def has_heated_seats(self) -> bool:
        return self.has_level_heated_seats or self.has_on_off_heated_seats

    @property
    def supports_target_soc(self) -> bool:
        return self.__get_property_by_code("BType") == "1"

    @property
    def real_battery_capacity(self) -> float | None:
        if (
            self.__custom_battery_capacity is not None
            and self.__custom_battery_capacity > 0
        ):
            return float(self.__custom_battery_capacity)

        result: float | None = None

        if self.series.startswith("EH32"):
            result = self.__mg4_real_battery_capacity
        elif self.series.startswith("AH4EM"):
            result = self.__mg4_urban_real_battery_capacity
        elif self.series.startswith("EC32"):
            result = self.__cyberster_real_battery_capacity
        elif self.series.startswith("EP2"):
            result = self.__mg5_real_battery_capacity
        elif self.series.startswith("ZS EV"):
            result = self.__zs_ev_real_battery_capacity
        elif self.series.startswith("MZS3E"):
            result = self.__mgs5_real_battery_capacity

        if result is None:
            LOG.warning(
                f"Unknown battery capacity for car series='{self.series}', model='{self.model}', "
                f"supports_target_soc={self.supports_target_soc}. Please file an issue to improve data accuracy"
            )
        return result

    @property
    def __mg4_real_battery_capacity(self) -> float | None:
        # MG4 Trophy Extended Range
        if self.model.startswith("EH32 X3"):
            return 77.0
        if self.supports_target_soc:
            # MG4 with NMC battery
            return 64.0
        # MG4 with LFP battery
        return 51.0

    @property
    def __mg4_urban_real_battery_capacity(self) -> float | None:
        # MG4 Urban is sold with a 43kWh and a 54kWh LFP pack, in several trims.
        # The series alone does not tell them apart: "AH4EM L" was reported as
        # 43kWh, while "AH4EM S" was reported both as 54kWh and as 43kWh.
        # Keep the historical guess, and tell the owner how to override it.
        if not self.__urban_capacity_hint_logged:
            self.__urban_capacity_hint_logged = True
            LOG.info(
                f"MG4 Urban series='{self.series}' is sold with a 43kWh and a 54kWh "
                "battery, and the series does not tell which one this car has. "
                "If the capacity is wrong, set BATTERY_CAPACITY_MAPPING "
                f"({self.vin}=43.0 or {self.vin}=54.0)"
            )
        if self.series == "AH4EM L":
            return 43.0
        return 54.0

    @property
    def __mgs5_real_battery_capacity(self) -> float | None:
        # From the datasheet
        # Battery pack type 1 (49kWh)
        # Battery pack type 2 (62.2kWh)
        # Battery pack type 3 (64kWh)
        if self.supports_target_soc:
            return 64.0
        return 49.0

    @property
    def __cyberster_real_battery_capacity(self) -> float | None:
        # Model: MG Cyberster
        return 72.5

    @property
    def __mg5_real_battery_capacity(self) -> float | None:
        # Model: MG5 Electric, variant MG5 SR Comfort
        if self.series.startswith("EP2CP3"):
            return 50.3
        # Model: MG5 Electric, variant MG5 MR Luxury
        if self.series.startswith("EP2DP3"):
            return 61.1
        return None

    @property
    def __zs_ev_real_battery_capacity(self) -> float | None:
        # Model: MG ZS EV 2021
        if self.supports_target_soc:
            # Long Range with NMC battery
            return 68.3
        # Standard Range with LFP battery
        return 49.0
