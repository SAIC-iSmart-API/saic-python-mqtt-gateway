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
        self.properties: Final[dict[str, dict[str, str | None]]] = (
            self.__properties_from_configuration(self.configuration)
        )
        self.__custom_battery_capacity: float | None = custom_battery_capacity

    @staticmethod
    def __properties_from_configuration(
        configuration: list[VehicleModelConfiguration],
    ) -> dict[str, dict[str, str | None]]:
        properties = {}
        for c in configuration:
            property_name = c.itemName
            property_code = c.itemCode
            property_value = c.itemValue
            if property_name is not None:
                properties[property_name] = {
                    "name": property_name,
                    "code": property_code,
                    "value": property_value,
                }
            if property_code is not None:
                properties[property_code] = {
                    "name": property_name,
                    "code": property_code,
                    "value": property_value,
                }
        return properties

    def get_ac_temperature_idx(self, remote_ac_temperature: int) -> int:
        if self.series.startswith("EH32"):
            return 3 + remote_ac_temperature - self.min_ac_temperature
        return 2 + remote_ac_temperature - self.min_ac_temperature

    @property
    def min_ac_temperature(self) -> int:
        if self.series.startswith("EH32"):
            return 17
        return 16

    @property
    def max_ac_temperature(self) -> int:
        if self.series.startswith("EH32"):
            return 33
        return 28

    def __get_property_value(self, property_name: str) -> str | None:
        if property_name in self.properties:
            pdict = self.properties[property_name]
            if pdict is not None and isinstance(pdict, dict) and "value" in pdict:
                return pdict["value"]
        return None

    @property
    def is_ev(self) -> bool:
        return not self.series.startswith("ZP22")

    @property
    def has_fossil_fuel(self) -> bool:
        return not self.is_ev

    @property
    def has_sunroof(self) -> bool:
        return self.__get_property_value("Sunroof") != "0"

    @property
    def has_on_off_heated_seats(self) -> bool:
        return self.__get_property_value("HeatedSeat") == "2"

    @property
    def has_level_heated_seats(self) -> bool:
        return self.__get_property_value("HeatedSeat") == "1"

    @property
    def has_heated_seats(self) -> bool:
        return self.has_level_heated_seats or self.has_on_off_heated_seats

    @property
    def supports_target_soc(self) -> bool:
        return self.__get_property_value("Battery") == "1"

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
        elif self.series.startswith("EP2"):
            result = self.__mg5_real_battery_capacity
        elif self.series.startswith("ZS EV"):
            result = self.__zs_ev_real_battery_capacity

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
