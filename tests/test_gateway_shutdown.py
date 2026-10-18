from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

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


class TestGatewayShutdown(unittest.IsolatedAsyncioTestCase):
    async def _run_with_main_loop(
        self, gateway: MqttGateway, main_loop: AsyncMock
    ) -> None:
        with (
            patch.object(gateway, "_MqttGateway__do_initial_login", AsyncMock()),
            patch.object(gateway, "_MqttGateway__run_until_all_tasks_done", main_loop),
            patch.object(gateway, "_MqttGateway__scheduler", create=True),
        ):
            await gateway.run()

    async def test_api_client_closed_when_main_loop_exits(self) -> None:
        gateway = _make_gateway()
        gateway.saic_api.close = AsyncMock()  # type: ignore[method-assign]

        with pytest.raises(SystemExit):
            await self._run_with_main_loop(
                gateway, AsyncMock(side_effect=SystemExit(-1))
            )

        gateway.saic_api.close.assert_awaited_once()

    async def test_close_failure_is_logged_not_raised(self) -> None:
        gateway = _make_gateway()
        gateway.saic_api.close = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]

        with self.assertLogs("mqtt_gateway", level="WARNING"):
            await self._run_with_main_loop(gateway, AsyncMock())

        gateway.saic_api.close.assert_awaited_once()

    async def test_publisher_flushed_before_api_client_closes(self) -> None:
        gateway = _make_gateway()
        order: list[str] = []
        gateway.saic_api.close = AsyncMock(  # type: ignore[method-assign]
            side_effect=lambda: order.append("close")
        )
        gateway.publisher.flush = AsyncMock(  # type: ignore[method-assign]
            side_effect=lambda: order.append("flush")
        )

        await self._run_with_main_loop(gateway, AsyncMock())

        assert order == ["flush", "close"]

    async def test_flush_failure_is_logged_not_raised(self) -> None:
        gateway = _make_gateway()
        gateway.saic_api.close = AsyncMock()  # type: ignore[method-assign]
        gateway.publisher.flush = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]

        with self.assertLogs("mqtt_gateway", level="WARNING"):
            await self._run_with_main_loop(gateway, AsyncMock())

        gateway.saic_api.close.assert_awaited_once()
