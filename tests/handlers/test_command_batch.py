from __future__ import annotations

import asyncio
import json
from typing import Any
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from saic_ismart_client_ng import SaicApi
from saic_ismart_client_ng.exceptions import SaicApiException

from handlers.vehicle_command import VehicleCommandHandler
from tests.common_mocks import VIN
from vehicle import RefreshMode

PREFIX = f"vehicles/{VIN}"
TOPIC = f"saic/{PREFIX}/commands/batch/set"
COMMAND = "climate/remoteClimateState/set"


class TestCommandBatch(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.api = AsyncMock(spec=SaicApi)
        self.state = MagicMock()
        self.state.vin = VIN
        self.state.get_ac_temperature_idx.return_value = 8
        self.handler = VehicleCommandHandler(
            vehicle_state=self.state,
            saic_api=self.api,
            relogin_handler=AsyncMock(),
            mqtt_topic="saic",
            vehicle_prefix=PREFIX,
        )

    def payload(self, count: int = 2) -> str:
        return json.dumps(
            {
                "requestId": "test",
                "commands": [{"topic": COMMAND, "payload": "on"} for _ in range(count)],
            }
        )

    def result(self) -> dict[str, Any]:
        value: dict[str, Any] = self.state.publisher.publish_json.call_args.args[1]
        return value

    async def test_sequence_refreshes_once(self) -> None:
        async def command(*_args: object, **_kwargs: object) -> None:
            assert self.handler.operation_lock.locked()
            self.state.set_refresh_mode.assert_not_called()

        self.api.start_ac.side_effect = command
        await self.handler.handle_mqtt_command(topic=TOPIC, payload=self.payload())
        assert self.api.start_ac.await_count == 2
        self.state.set_refresh_mode.assert_called_once_with(
            RefreshMode.FORCE, "after batch execution"
        )
        assert self.result() == {
            "requestId": "test",
            "status": "success",
            "results": [
                {"topic": COMMAND, "status": "success"},
                {"topic": COMMAND, "status": "success"},
            ],
        }
        self.state.publisher.clear_topic.assert_called_once_with(
            f"{PREFIX}/commands/batch/set"
        )
        assert not self.handler.operation_lock.locked()

    async def test_failure_stops_and_refreshes(self) -> None:
        self.api.start_ac.side_effect = [None, SaicApiException("busy")]
        await self.handler.handle_mqtt_command(topic=TOPIC, payload=self.payload(3))
        assert self.api.start_ac.await_count == 2
        assert self.result()["status"] == "failed"
        assert [r["status"] for r in self.result()["results"]] == [
            "success",
            "failed",
            "skipped",
        ]
        self.state.set_refresh_mode.assert_called_once()

    async def test_validate_entire_envelope_before_execution(self) -> None:
        for topic in (
            "commands/batch/set",
            "refresh/mode/set",
            "other/vehicles/id/climate/remoteClimateState/set",
            "unsupported/set",
        ):
            data = json.loads(self.payload())
            data["commands"][1]["topic"] = topic
            await self.handler.handle_mqtt_command(
                topic=TOPIC, payload=json.dumps(data)
            )
            assert self.result()["status"] == "invalid"
        for value in (
            "{",
            "[]",
            "{}",
            '{"commands":[]}',
            self.payload(33),
            "x" * 65537,
        ):
            await self.handler.handle_mqtt_command(topic=TOPIC, payload=value)
            assert self.result()["status"] == "invalid"
        self.api.start_ac.assert_not_awaited()
        self.state.set_refresh_mode.assert_not_called()

    async def test_empty_and_retained_are_ignored(self) -> None:
        await self.handler.handle_mqtt_command(
            topic=TOPIC, payload=self.payload(), retained=True
        )
        await self.handler.handle_mqtt_command(topic=TOPIC, payload="")
        self.api.start_ac.assert_not_awaited()
        self.state.publisher.publish_json.assert_not_called()

    async def test_single_command_waits_for_batch(self) -> None:
        started, release = asyncio.Event(), asyncio.Event()

        async def command(*_args: object, **_kwargs: object) -> None:
            started.set()
            await release.wait()

        self.api.start_ac.side_effect = command
        batch = asyncio.create_task(
            self.handler.handle_mqtt_command(topic=TOPIC, payload=self.payload(1))
        )
        await started.wait()
        single = asyncio.create_task(
            self.handler.handle_mqtt_command(
                topic=f"saic/{PREFIX}/{COMMAND}", payload="off"
            )
        )
        await asyncio.sleep(0)
        self.api.stop_ac.assert_not_awaited()
        release.set()
        await asyncio.gather(batch, single)
        self.api.stop_ac.assert_awaited_once()

    async def test_timeout_releases_lock_and_refreshes(self) -> None:
        original_timeout = asyncio.timeout

        async def slow(*_args: object, **_kwargs: object) -> None:
            await asyncio.sleep(10)

        self.api.start_ac.side_effect = slow
        with patch(
            "handlers.vehicle_command.asyncio.timeout",
            side_effect=lambda _: original_timeout(0.01),
        ):
            await self.handler.handle_mqtt_command(topic=TOPIC, payload=self.payload())
        assert self.result()["status"] == "failed"
        assert self.result()["results"][0]["status"] == "unknown"
        self.state.set_refresh_mode.assert_called_once()
        assert not self.handler.operation_lock.locked()

    async def test_cancel_releases_lock_and_refreshes(self) -> None:
        started = asyncio.Event()

        async def slow(*_args: object, **_kwargs: object) -> None:
            started.set()
            await asyncio.sleep(10)

        self.api.start_ac.side_effect = slow
        task = asyncio.create_task(
            self.handler.handle_mqtt_command(topic=TOPIC, payload=self.payload())
        )
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert self.result()["status"] == "cancelled"
        self.state.set_refresh_mode.assert_called_once()
        assert not self.handler.operation_lock.locked()
