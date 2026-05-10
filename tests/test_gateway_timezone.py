from __future__ import annotations

import logging
import unittest
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from saic_ismart_client_ng.api.user import UserTimezoneResp

from configuration import Configuration
from mqtt_gateway import MqttGateway
import mqtt_topics

from .mocks import MessageCapturingConsolePublisher


def _make_gateway(config: Configuration) -> MqttGateway:
    with patch(
        "mqtt_gateway.MqttGateway._MqttGateway__select_publisher",
        return_value=MessageCapturingConsolePublisher(config),
    ):
        return MqttGateway(config)


def _make_config(*, forced_tz: ZoneInfo | None) -> Configuration:
    config = Configuration()
    config.saic_user = "user@example.com"
    config.saic_password = "secret"  # noqa: S105
    config.saic_user_timezone = forced_tz
    return config


# Name-mangled access helpers — mypy does not see private dunder names.
async def _refresh(gateway: MqttGateway) -> None:
    await gateway._MqttGateway__refresh_user_timezone()  # type: ignore[attr-defined]


def _user_tz(gateway: MqttGateway) -> ZoneInfo | None:
    tz: ZoneInfo | None = gateway._MqttGateway__user_timezone  # type: ignore[attr-defined]
    return tz


class TestGatewayTimezoneRefresh(unittest.IsolatedAsyncioTestCase):
    async def test_uses_api_timezone_when_no_override(self) -> None:
        config = _make_config(forced_tz=None)
        gateway = _make_gateway(config)
        publisher = gateway.publisher
        assert isinstance(publisher, MessageCapturingConsolePublisher)

        with patch.object(
            gateway.saic_api,
            "get_user_timezone",
            new=AsyncMock(return_value=UserTimezoneResp(timezone="GMT+10:00")),
        ):
            await _refresh(gateway)

        assert (
            publisher.map[f"user@example.com/{mqtt_topics.ACCOUNT_USER_TIMEZONE}"]
            == "Etc/GMT-10"
        )

    async def test_forced_timezone_overrides_api_with_offset_mismatch(self) -> None:
        # Sydney is currently at GMT+11 (DST) or GMT+10; pick a forced zone
        # whose current offset does not match what the API returned.
        forced = ZoneInfo("Europe/Rome")
        config = _make_config(forced_tz=forced)
        gateway = _make_gateway(config)
        publisher = gateway.publisher
        assert isinstance(publisher, MessageCapturingConsolePublisher)

        with (
            patch.object(
                gateway.saic_api,
                "get_user_timezone",
                new=AsyncMock(return_value=UserTimezoneResp(timezone="GMT+11:00")),
            ),
            self.assertLogs("mqtt_gateway", level=logging.WARNING) as cm,
        ):
            await _refresh(gateway)

        assert (
            publisher.map[f"user@example.com/{mqtt_topics.ACCOUNT_USER_TIMEZONE}"]
            == "Europe/Rome"
        )
        joined = "\n".join(cm.output)
        assert "Europe/Rome" in joined
        assert "Etc/GMT-11" in joined
        assert "differs from API value" in joined

    async def test_forced_timezone_used_when_api_fails(self) -> None:
        forced = ZoneInfo("Australia/Sydney")
        config = _make_config(forced_tz=forced)
        gateway = _make_gateway(config)
        publisher = gateway.publisher
        assert isinstance(publisher, MessageCapturingConsolePublisher)

        with patch.object(
            gateway.saic_api,
            "get_user_timezone",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            await _refresh(gateway)

        assert (
            publisher.map[f"user@example.com/{mqtt_topics.ACCOUNT_USER_TIMEZONE}"]
            == "Australia/Sydney"
        )

    def test_forced_timezone_primed_at_construction(self) -> None:
        forced = ZoneInfo("Australia/Sydney")
        config = _make_config(forced_tz=forced)
        gateway = _make_gateway(config)
        # Vehicles created during initial discovery (before
        # __refresh_user_timezone runs) must already see the forced zone.
        assert _user_tz(gateway) == forced

    async def test_no_warning_when_iana_zone_matches_api_offset(self) -> None:
        # Same instant: Etc/GMT-10 has offset +10:00; an IANA zone fixed at +10
        # year-round (no DST) should be considered equivalent.
        forced = ZoneInfo("Australia/Brisbane")  # AEST, +10 year-round
        config = _make_config(forced_tz=forced)
        gateway = _make_gateway(config)

        logger = logging.getLogger("mqtt_gateway")
        with (
            patch.object(
                gateway.saic_api,
                "get_user_timezone",
                new=AsyncMock(return_value=UserTimezoneResp(timezone="GMT+10:00")),
            ),
            patch.object(logger, "warning") as mock_warning,
        ):
            await _refresh(gateway)

        for call in mock_warning.call_args_list:
            assert "differs from API value" not in str(call)
