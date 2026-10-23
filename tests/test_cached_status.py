from __future__ import annotations

import datetime
import time
import unittest
from unittest.mock import MagicMock

from apscheduler.schedulers.blocking import BlockingScheduler
import pytest
from saic_ismart_client_ng.api.vehicle import (
    BasicVehicleStatus,
    VehicleStatusCacheResp,
)
from saic_ismart_client_ng.api.vehicle.schema import VinInfo

from configuration import Configuration
from handlers.command.base import RESULT_DO_NOTHING
from handlers.command.gateway.refresh_period import RefreshPeriodCachedStatusCommand
import mqtt_topics
from status_publisher.vehicle.cached_status import (
    CachedStatusState,
    check_cached_status,
)
from vehicle import RefreshMode, VehicleState
from vehicle_info import VehicleInfo

from .common_mocks import VIN
from .mocks import MessageCapturingConsolePublisher

NOW = int(time.time())
NO_STATE = CachedStatusState(
    last_live_status_time=None,
    last_cached_status_time=None,
    last_known_mileage=None,
)


def make_cached(
    *,
    status_time: int | None = NOW,
    mileage: int | None = 123450,
    soc: int | None = 80,
    electric_range: int | None = 3200,
    charging: int | None = 0,
    engine_status: int | None = 0,
) -> VehicleStatusCacheResp:
    return VehicleStatusCacheResp(
        statusTime=status_time,
        onlineStatus=1,
        basicVehicleStatus=BasicVehicleStatus(
            mileage=mileage,
            extendedData1=soc,
            extendedData2=charging,
            fuelRangeElec=electric_range,
            engineStatus=engine_status,
            lockStatus=1,
        ),
    )


class TestCheckCachedStatus:
    def test_plausible_status_is_accepted(self) -> None:
        assert check_cached_status(make_cached(), NO_STATE) is None

    def test_missing_basic_status_is_rejected(self) -> None:
        cached = VehicleStatusCacheResp(statusTime=NOW)
        assert check_cached_status(cached, NO_STATE) is not None

    @pytest.mark.parametrize("status_time", [None, 0, 2147483647])
    def test_invalid_status_time_is_rejected(self, status_time: int | None) -> None:
        assert (
            check_cached_status(make_cached(status_time=status_time), NO_STATE)
            is not None
        )

    def test_status_time_in_the_future_is_rejected(self) -> None:
        cached = make_cached(status_time=NOW + 3600)
        assert check_cached_status(cached, NO_STATE) is not None

    def test_unchanged_status_time_is_rejected(self) -> None:
        state = CachedStatusState(
            last_live_status_time=None,
            last_cached_status_time=NOW,
            last_known_mileage=None,
        )
        assert check_cached_status(make_cached(status_time=NOW), state) is not None

    def test_status_not_newer_than_live_is_rejected(self) -> None:
        state = CachedStatusState(
            last_live_status_time=NOW,
            last_cached_status_time=None,
            last_known_mileage=None,
        )
        assert check_cached_status(make_cached(status_time=NOW), state) is not None
        assert check_cached_status(make_cached(status_time=NOW - 60), state) is not None
        assert check_cached_status(make_cached(status_time=NOW + 1), state) is None

    @pytest.mark.parametrize("mileage", [None, 0, 65535, 2147483647])
    def test_invalid_mileage_is_rejected(self, mileage: int | None) -> None:
        assert check_cached_status(make_cached(mileage=mileage), NO_STATE) is not None

    def test_decreasing_mileage_is_rejected(self) -> None:
        state = CachedStatusState(
            last_live_status_time=None,
            last_cached_status_time=None,
            last_known_mileage=200000,
        )
        assert check_cached_status(make_cached(mileage=199990), state) is not None
        assert check_cached_status(make_cached(mileage=200000), state) is None
        assert check_cached_status(make_cached(mileage=200010), state) is None

    @pytest.mark.parametrize("soc", [0, 65535, 101])
    def test_invalid_soc_is_rejected(self, soc: int) -> None:
        assert check_cached_status(make_cached(soc=soc), NO_STATE) is not None

    def test_missing_soc_is_accepted(self) -> None:
        assert check_cached_status(make_cached(soc=None), NO_STATE) is None

    @pytest.mark.parametrize("electric_range", [0, 65535])
    def test_invalid_range_is_rejected(self, electric_range: int) -> None:
        cached = make_cached(electric_range=electric_range)
        assert check_cached_status(cached, NO_STATE) is not None


class TestVehicleStateCachedStatus(unittest.TestCase):
    def setUp(self) -> None:
        config = Configuration()
        config.anonymized_publishing = False
        self.publisher = MessageCapturingConsolePublisher(config)
        vin_info = VinInfo()
        vin_info.vin = VIN
        self.vehicle_state = VehicleState(
            self.publisher,
            BlockingScheduler(),
            f"/vehicles/{VIN}",
            VehicleInfo(vin_info, None),
            default_refresh_period_cached_status=900,
        )

    def topic(self, sub_topic: str) -> str:
        return f"/vehicles/{VIN}/{sub_topic}"

    def make_inactive(self) -> None:
        self.vehicle_state.configure_missing()
        self.vehicle_state.hv_battery_active = False
        self.vehicle_state.last_car_shutdown = datetime.datetime.min.replace(
            tzinfo=datetime.UTC
        )

    def test_default_comes_from_configuration(self) -> None:
        assert self.vehicle_state.refresh_period_cached_status == -1
        self.vehicle_state.configure_missing()
        assert self.vehicle_state.refresh_period_cached_status == 900
        assert (
            self.publisher.map[self.topic(mqtt_topics.REFRESH_PERIOD_CACHED_STATUS)]
            == 900
        )

    def test_retained_value_beats_configuration_default(self) -> None:
        self.vehicle_state.set_refresh_period_cached_status(300)
        self.vehicle_state.configure_missing()
        assert self.vehicle_state.refresh_period_cached_status == 300

    def test_zero_is_kept_and_disables_reading(self) -> None:
        self.vehicle_state.set_refresh_period_cached_status(0)
        self.vehicle_state.configure_missing()
        assert self.vehicle_state.refresh_period_cached_status == 0
        assert not self.vehicle_state.should_refresh_cached_status(
            ignore_vehicle_state=True
        )

    def test_republish_includes_cached_status_period(self) -> None:
        self.vehicle_state.set_refresh_period_cached_status(600)
        self.publisher.map.clear()
        self.vehicle_state.republish_command_states()
        assert (
            self.publisher.map[self.topic(mqtt_topics.REFRESH_PERIOD_CACHED_STATUS)]
            == 600
        )

    def test_not_republished_when_unset(self) -> None:
        self.vehicle_state.republish_command_states()
        assert (
            self.topic(mqtt_topics.REFRESH_PERIOD_CACHED_STATUS)
            not in self.publisher.map
        )

    def test_does_not_gate_polling_configuration(self) -> None:
        self.vehicle_state.set_refresh_period_active(30)
        self.vehicle_state.set_refresh_period_inactive(86400)
        self.vehicle_state.set_refresh_period_after_shutdown(120)
        self.vehicle_state.set_refresh_period_inactive_grace(600)
        assert self.vehicle_state.refresh_period_cached_status == -1
        assert self.vehicle_state.is_complete()

    def test_refresh_when_inactive_and_due(self) -> None:
        self.make_inactive()
        assert self.vehicle_state.should_refresh_cached_status(
            ignore_vehicle_state=False
        )

    def test_no_refresh_before_period_elapsed(self) -> None:
        self.make_inactive()
        self.vehicle_state.mark_cached_status_poll()
        assert not self.vehicle_state.should_refresh_cached_status(
            ignore_vehicle_state=False
        )
        assert not self.vehicle_state.should_refresh_cached_status(
            ignore_vehicle_state=True
        )

    def test_no_refresh_while_hv_battery_active(self) -> None:
        self.make_inactive()
        self.vehicle_state.hv_battery_active = True
        assert not self.vehicle_state.should_refresh_cached_status(
            ignore_vehicle_state=False
        )
        assert self.vehicle_state.should_refresh_cached_status(
            ignore_vehicle_state=True
        )

    def test_no_refresh_while_charging(self) -> None:
        self.make_inactive()
        self.vehicle_state.set_is_charging(is_charging=True)
        self.vehicle_state.hv_battery_active = False
        assert not self.vehicle_state.should_refresh_cached_status(
            ignore_vehicle_state=False
        )
        assert self.vehicle_state.should_refresh_cached_status(
            ignore_vehicle_state=True
        )

    def test_no_refresh_during_shutdown_grace_period(self) -> None:
        self.make_inactive()
        self.vehicle_state.last_car_shutdown = datetime.datetime.now(tz=datetime.UTC)
        assert not self.vehicle_state.should_refresh_cached_status(
            ignore_vehicle_state=False
        )

    def test_refresh_mode_off_only_ignored_in_debug_mode(self) -> None:
        self.make_inactive()
        self.vehicle_state.refresh_mode = RefreshMode.OFF
        assert not self.vehicle_state.should_refresh_cached_status(
            ignore_vehicle_state=False
        )
        assert self.vehicle_state.should_refresh_cached_status(
            ignore_vehicle_state=True
        )

    def test_accepted_status_is_published(self) -> None:
        assert self.vehicle_state.handle_cached_status(make_cached()) is True
        assert self.publisher.map[self.topic(mqtt_topics.DRIVETRAIN_MILEAGE)] == 12345.0
        assert self.publisher.map[self.topic(mqtt_topics.DRIVETRAIN_SOC)] == 80.0
        assert self.publisher.map[self.topic(mqtt_topics.DRIVETRAIN_RANGE)] == 320.0
        assert self.publisher.map[self.topic(mqtt_topics.DOORS_LOCKED)] is True
        assert self.vehicle_state.last_cached_status_time == NOW
        assert self.vehicle_state.last_known_mileage == 123450

    def test_rejected_status_publishes_nothing(self) -> None:
        assert self.vehicle_state.handle_cached_status(make_cached(soc=0)) is False
        assert self.topic(mqtt_topics.DRIVETRAIN_SOC) not in self.publisher.map
        assert self.topic(mqtt_topics.DRIVETRAIN_MILEAGE) not in self.publisher.map
        assert self.vehicle_state.last_cached_status_time is None

    def test_same_status_time_is_published_once(self) -> None:
        assert self.vehicle_state.handle_cached_status(make_cached()) is True
        assert self.vehicle_state.handle_cached_status(make_cached()) is False

    def test_mileage_cannot_go_back(self) -> None:
        assert self.vehicle_state.handle_cached_status(make_cached()) is True
        older = make_cached(status_time=NOW + 60, mileage=123000)
        assert self.vehicle_state.handle_cached_status(older) is False
        assert self.publisher.map[self.topic(mqtt_topics.DRIVETRAIN_MILEAGE)] == 12345.0

    def test_cache_does_not_change_vehicle_activity_state(self) -> None:
        self.vehicle_state.hv_battery_active = False
        self.vehicle_state.set_is_charging(is_charging=False)
        cached = make_cached(charging=1, engine_status=1)
        assert self.vehicle_state.handle_cached_status(cached) is True
        assert not self.vehicle_state.hv_battery_active
        assert not self.vehicle_state.is_charging

    def test_cache_does_not_touch_live_refresh_bookkeeping(self) -> None:
        before = self.vehicle_state.last_successful_refresh
        self.vehicle_state.handle_cached_status(make_cached())
        assert self.vehicle_state.last_successful_refresh == before
        assert (
            self.topic(mqtt_topics.REFRESH_LAST_VEHICLE_STATE) not in self.publisher.map
        )


class TestRefreshPeriodCachedStatusCommand(unittest.IsolatedAsyncioTestCase):
    def test_topic(self) -> None:
        assert (
            RefreshPeriodCachedStatusCommand.topic()
            == mqtt_topics.REFRESH_PERIOD_CACHED_STATUS_SET
        )
        assert RefreshPeriodCachedStatusCommand.is_replayable_when_retained()

    async def test_sets_period(self) -> None:
        vehicle_state = MagicMock()
        handler = RefreshPeriodCachedStatusCommand(MagicMock(), vehicle_state)
        assert await handler.handle("900") == RESULT_DO_NOTHING
        vehicle_state.set_refresh_period_cached_status.assert_called_once_with(900)

    async def test_negative_period_disables(self) -> None:
        vehicle_state = MagicMock()
        handler = RefreshPeriodCachedStatusCommand(MagicMock(), vehicle_state)
        await handler.handle("-5")
        vehicle_state.set_refresh_period_cached_status.assert_called_once_with(0)
