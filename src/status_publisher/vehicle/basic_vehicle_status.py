from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import mqtt_topics
from status_publisher import VehicleDataPublisher
from utils import int_to_bool, is_valid_temperature, to_remote_climate, value_in_range

if TYPE_CHECKING:
    from saic_ismart_client_ng.api.vehicle import BasicVehicleStatus

PRESSURE_TO_BAR_FACTOR = 0.04


@dataclass(kw_only=True, frozen=True)
class BasicVehicleStatusProcessingResult:
    hv_battery_active_from_car: bool
    remote_ac_running: bool
    remote_heated_seats_front_right_level: int | None
    remote_heated_seats_front_left_level: int | None
    is_parked: bool
    fuel_rage_elec: int | None
    raw_soc: int | None


class BasicVehicleStatusPublisher(VehicleDataPublisher):
    def on_basic_vehicle_status(
        self, basic_vehicle_status: BasicVehicleStatus
    ) -> BasicVehicleStatusProcessingResult:
        is_engine_running = basic_vehicle_status.is_engine_running
        remote_climate_status = basic_vehicle_status.remoteClimateStatus or 0
        rear_window_heat_state = basic_vehicle_status.rmtHtdRrWndSt or 0

        hv_battery_active_from_car = (
            is_engine_running or remote_climate_status > 0 or rear_window_heat_state > 0
        )

        is_valid_mileage, _ = self._transform_and_publish(
            topic=mqtt_topics.DRIVETRAIN_MILEAGE,
            value=basic_vehicle_status.mileage,
            validator=lambda x: value_in_range(x, 1, 2147483647),
            transform=lambda x: x / 10.0,
        )

        self._publish(
            topic=mqtt_topics.DRIVETRAIN_RUNNING,
            value=is_engine_running,
        )

        self._publish(
            topic=mqtt_topics.CLIMATE_INTERIOR_TEMPERATURE,
            value=basic_vehicle_status.interiorTemperature,
            validator=is_valid_temperature,
        )

        self._publish(
            topic=mqtt_topics.CLIMATE_EXTERIOR_TEMPERATURE,
            value=basic_vehicle_status.exteriorTemperature,
            validator=is_valid_temperature,
        )

        self._transform_and_publish(
            topic=mqtt_topics.DRIVETRAIN_AUXILIARY_BATTERY_VOLTAGE,
            value=basic_vehicle_status.batteryVoltage,
            validator=lambda x: value_in_range(x, 1, 65535),
            transform=lambda x: x / 10.0,
        )

        if is_valid_mileage:
            self._transform_and_publish(
                topic=mqtt_topics.WINDOWS_DRIVER,
                value=basic_vehicle_status.driverWindow,
                transform=int_to_bool,
            )

            self._transform_and_publish(
                topic=mqtt_topics.WINDOWS_PASSENGER,
                value=basic_vehicle_status.passengerWindow,
                transform=int_to_bool,
            )

            self._transform_and_publish(
                topic=mqtt_topics.WINDOWS_REAR_LEFT,
                value=basic_vehicle_status.rearLeftWindow,
                transform=int_to_bool,
            )

            self._transform_and_publish(
                topic=mqtt_topics.WINDOWS_REAR_RIGHT,
                value=basic_vehicle_status.rearRightWindow,
                transform=int_to_bool,
            )

        self._transform_and_publish(
            topic=mqtt_topics.WINDOWS_SUN_ROOF,
            value=basic_vehicle_status.sunroofStatus,
            transform=int_to_bool,
        )

        self._transform_and_publish(
            topic=mqtt_topics.DOORS_LOCKED,
            value=basic_vehicle_status.lockStatus,
            transform=int_to_bool,
        )

        self._transform_and_publish(
            topic=mqtt_topics.DOORS_DRIVER,
            value=basic_vehicle_status.driverDoor,
            transform=int_to_bool,
        )

        self._transform_and_publish(
            topic=mqtt_topics.DOORS_PASSENGER,
            value=basic_vehicle_status.passengerDoor,
            transform=int_to_bool,
        )

        self._transform_and_publish(
            topic=mqtt_topics.DOORS_REAR_LEFT,
            value=basic_vehicle_status.rearLeftDoor,
            transform=int_to_bool,
        )

        self._transform_and_publish(
            topic=mqtt_topics.DOORS_REAR_RIGHT,
            value=basic_vehicle_status.rearRightDoor,
            transform=int_to_bool,
        )

        self._transform_and_publish(
            topic=mqtt_topics.DOORS_BONNET,
            value=basic_vehicle_status.bonnetStatus,
            transform=int_to_bool,
        )

        self._transform_and_publish(
            topic=mqtt_topics.DOORS_BOOT,
            value=basic_vehicle_status.bootStatus,
            transform=int_to_bool,
        )

        self.__publish_tyre(
            basic_vehicle_status.frontLeftTyrePressure,
            mqtt_topics.TYRES_FRONT_LEFT_PRESSURE,
        )

        self.__publish_tyre(
            basic_vehicle_status.frontRightTyrePressure,
            mqtt_topics.TYRES_FRONT_RIGHT_PRESSURE,
        )
        self.__publish_tyre(
            basic_vehicle_status.rearLeftTyrePressure,
            mqtt_topics.TYRES_REAR_LEFT_PRESSURE,
        )
        self.__publish_tyre(
            basic_vehicle_status.rearRightTyrePressure,
            mqtt_topics.TYRES_REAR_RIGHT_PRESSURE,
        )

        self._transform_and_publish(
            topic=mqtt_topics.LIGHTS_MAIN_BEAM,
            value=basic_vehicle_status.mainBeamStatus,
            transform=int_to_bool,
        )

        self._transform_and_publish(
            topic=mqtt_topics.LIGHTS_DIPPED_BEAM,
            value=basic_vehicle_status.dippedBeamStatus,
            transform=int_to_bool,
        )

        self._transform_and_publish(
            topic=mqtt_topics.LIGHTS_SIDE,
            value=basic_vehicle_status.sideLightStatus,
            transform=int_to_bool,
        )

        self._transform_and_publish(
            topic=mqtt_topics.CLIMATE_REMOTE_CLIMATE_STATE,
            value=remote_climate_status,
            transform=lambda x: to_remote_climate(x),
        )

        remote_ac_running = remote_climate_status == 2

        self._transform_and_publish(
            topic=mqtt_topics.CLIMATE_BACK_WINDOW_HEAT,
            value=rear_window_heat_state,
            transform=lambda x: "off" if x == 0 else "on",
        )

        _, front_left_seat_level = self._publish(
            topic=mqtt_topics.CLIMATE_HEATED_SEATS_FRONT_LEFT_LEVEL,
            value=basic_vehicle_status.frontLeftSeatHeatLevel,
            validator=lambda x: value_in_range(x, 0, 255),
        )

        _, front_right_seat_level = self._publish(
            topic=mqtt_topics.CLIMATE_HEATED_SEATS_FRONT_RIGHT_LEVEL,
            value=basic_vehicle_status.frontRightSeatHeatLevel,
            validator=lambda x: value_in_range(x, 0, 255),
        )

        # Standard fossil fuels vehicles
        self._transform_and_publish(
            topic=mqtt_topics.DRIVETRAIN_FOSSIL_FUEL_RANGE,
            value=basic_vehicle_status.fuelRange,
            validator=lambda x: value_in_range(x, 0, 65535),
            transform=lambda x: x / 10.0,
        )

        self._publish(
            topic=mqtt_topics.DRIVETRAIN_FOSSIL_FUEL_PERCENTAGE,
            value=basic_vehicle_status.fuelLevelPrc,
            validator=lambda x: value_in_range(x, 0, 100, is_max_excl=False),
        )

        if (journey_id := basic_vehicle_status.currentJourneyId) is not None and (
            journey_distance := basic_vehicle_status.currentJourneyDistance
        ) is not None:
            self._publish(
                topic=mqtt_topics.DRIVETRAIN_CURRENT_JOURNEY,
                value={
                    "id": journey_id,
                    "distance": round(journey_distance / 10.0, 1),
                },
            )
        return BasicVehicleStatusProcessingResult(
            hv_battery_active_from_car=hv_battery_active_from_car,
            remote_ac_running=remote_ac_running,
            is_parked=basic_vehicle_status.is_parked,
            remote_heated_seats_front_left_level=front_left_seat_level,
            remote_heated_seats_front_right_level=front_right_seat_level,
            fuel_rage_elec=basic_vehicle_status.fuelRangeElec,
            raw_soc=basic_vehicle_status.extendedData1,
        )

    def __publish_tyre(self, raw_value: int | None, topic: str) -> None:
        self._transform_and_publish(
            topic=topic,
            value=raw_value,
            validator=lambda x: value_in_range(x, 1, 255),
            transform=lambda x: round(x * PRESSURE_TO_BAR_FACTOR, 2),
        )
