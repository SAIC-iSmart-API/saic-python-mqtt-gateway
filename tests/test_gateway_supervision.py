from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any
import unittest
from unittest.mock import patch

import pytest

from configuration import Configuration
from mqtt_gateway import MqttGateway

from .mocks import MessageCapturingConsolePublisher


def _make_gateway() -> MqttGateway:
    config = Configuration()
    config.saic_user = "user@example.com"
    config.saic_password = "secret"  # noqa: S105
    with patch(
        "mqtt_gateway.MqttGateway._MqttGateway__select_publisher",
        return_value=MessageCapturingConsolePublisher(config),
    ):
        return MqttGateway(config)


async def _supervise(
    gateway: MqttGateway, transport_task: asyncio.Task[Any] | None
) -> None:
    run = gateway._MqttGateway__run_until_all_tasks_done  # type: ignore[attr-defined]
    with patch.object(
        gateway.publisher, "connection_task", return_value=transport_task
    ):
        await asyncio.wait_for(run(), timeout=0.2)


class TestTransportSupervision(unittest.IsolatedAsyncioTestCase):
    async def test_exits_when_transport_task_crashes(self) -> None:
        async def crash() -> None:
            msg = "boom"
            raise RuntimeError(msg)

        task = asyncio.get_running_loop().create_task(crash())

        with self.assertLogs("mqtt_gateway", level="ERROR"), pytest.raises(SystemExit):
            await _supervise(_make_gateway(), task)

    async def test_exits_when_transport_task_ends_cleanly(self) -> None:
        async def finish() -> None:
            return None

        task = asyncio.get_running_loop().create_task(finish())

        with self.assertLogs("mqtt_gateway", level="ERROR"), pytest.raises(SystemExit):
            await _supervise(_make_gateway(), task)

    async def test_keeps_running_while_transport_task_is_alive(self) -> None:
        task = asyncio.get_running_loop().create_task(asyncio.sleep(10))

        with pytest.raises(TimeoutError):
            await _supervise(_make_gateway(), task)

        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def test_keeps_running_without_a_transport(self) -> None:
        """MQTT can be disabled (e.g. to only feed ABRP): nothing to supervise."""
        with pytest.raises(TimeoutError):
            await _supervise(_make_gateway(), None)

    async def test_default_publisher_has_no_connection_task(self) -> None:
        assert _make_gateway().publisher.connection_task() is None
