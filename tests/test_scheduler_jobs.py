from __future__ import annotations

import datetime
import inspect
from typing import TYPE_CHECKING
import unittest
from unittest.mock import AsyncMock, patch

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from saic_ismart_client_ng.api.vehicle.schema import VinInfo
from saic_ismart_client_ng.api.vehicle_charging import ScheduledChargingMode

from configuration import Configuration
from mqtt_gateway import MqttGateway
from vehicle import VehicleState
from vehicle_info import VehicleInfo

from .common_mocks import VIN
from .mocks import MessageCapturingConsolePublisher

if TYPE_CHECKING:
    from apscheduler.job import Job


class TestSchedulerJobsRunOnEventLoop(unittest.IsolatedAsyncioTestCase):
    """Every scheduled job must be a coroutine function.

    AsyncIOScheduler runs synchronous jobs in a worker thread, where the MQTT
    publisher (bound to the event loop) and the polling state are not safe to use.
    """

    @staticmethod
    def _assert_all_coroutines(jobs: list[Job]) -> None:
        assert jobs, "expected at least one scheduled job"
        sync_jobs = [j.id for j in jobs if not inspect.iscoroutinefunction(j.func)]
        assert not sync_jobs, f"jobs would run in a worker thread: {sync_jobs}"

    async def test_all_gateway_jobs_are_coroutines(self) -> None:
        config = Configuration()
        config.saic_user = "user@example.com"
        config.saic_password = "secret"  # noqa: S105
        with patch(
            "mqtt_gateway.MqttGateway._MqttGateway__select_publisher",
            return_value=MessageCapturingConsolePublisher(config),
        ):
            gateway = MqttGateway(config)
        gateway.saic_api.close = AsyncMock()  # type: ignore[method-assign]
        scheduler: AsyncIOScheduler = gateway._MqttGateway__scheduler  # type: ignore[attr-defined]
        relogin_handler = gateway._MqttGateway__relogin_handler  # type: ignore[attr-defined]

        with (
            patch.object(gateway, "_MqttGateway__do_initial_login", AsyncMock()),
            patch.object(
                gateway, "_MqttGateway__run_until_all_tasks_done", AsyncMock()
            ),
            patch.object(scheduler, "start"),
        ):
            await gateway.run()
        relogin_handler.relogin()

        self._assert_all_coroutines(scheduler.get_jobs())

    async def test_vehicle_jobs_are_coroutines(self) -> None:
        scheduler = AsyncIOScheduler()
        vin_info = VinInfo()
        vin_info.vin = VIN
        state = VehicleState(
            MessageCapturingConsolePublisher(Configuration()),
            scheduler,
            f"/vehicles/{VIN}",
            VehicleInfo(vin_info, None),
        )
        state.update_scheduled_charging(
            datetime.time(hour=23, minute=10),
            ScheduledChargingMode.UNTIL_CONFIGURED_TIME,
        )

        self._assert_all_coroutines(scheduler.get_jobs())
