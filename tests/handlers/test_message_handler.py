from __future__ import annotations

import datetime
import unittest
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

from saic_ismart_client_ng.api.message.schema import MessageEntity, MessageResp

from handlers.message import MessageHandler
from vehicle import RefreshMode

VIN = "vin_test_000000000"


def _message(
    message_id: str,
    message_time: str | None = None,
    *,
    message_type: str = "323",
) -> MessageEntity:
    return MessageEntity(
        messageId=message_id,
        messageTime=message_time,
        messageType=message_type,
        readStatus=0,
        title=f"Title {message_id}",
        vin=VIN,
    )


class TestMessageHandler(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.vehicle_handler = MagicMock()
        self.vehicle_handler.vehicle_state.refresh_mode = RefreshMode.PERIODIC
        self.gateway = MagicMock()
        self.gateway.vehicle_handlers = {VIN: self.vehicle_handler}
        self.gateway.get_vehicle_handler = MagicMock(return_value=self.vehicle_handler)
        self.relogin_handler = MagicMock()
        self.relogin_handler.relogin_in_progress = False
        self.saicapi = AsyncMock()
        self.handler = MessageHandler(
            gateway=self.gateway,
            relogin_handler=self.relogin_handler,
            saicapi=self.saicapi,
        )

    def _serve_pages(self, *messages: MessageEntity) -> None:
        """Serve one message per page, then an empty page."""
        pages = [MessageResp(messages=[m]) for m in messages]
        pages.append(MessageResp(messages=[]))
        self.saicapi.get_alarm_list = AsyncMock(side_effect=pages)

    def _notified(self) -> list[MessageEntity]:
        notify = self.vehicle_handler.vehicle_state.notify_message
        return [c.args[0] for c in notify.call_args_list]

    async def test_last_message_time_is_converted_to_utc(self) -> None:
        self._serve_pages(_message("m1", "2026-07-15 10:00:00"))

        await self.handler.check_for_new_messages()

        assert self.handler.last_message_ts == datetime.datetime(
            2026, 7, 15, 8, 0, tzinfo=datetime.UTC
        )
        assert self.handler.last_message_id == "m1"

    async def test_message_without_time_is_not_the_latest(self) -> None:
        timed = _message("timed", "2026-03-14 10:00:00")
        untimed = _message("untimed")
        self._serve_pages(untimed, timed)

        await self.handler.check_for_new_messages()

        assert self._notified() == [timed]
        assert self.handler.last_message_id == "timed"
        assert self.handler.last_message_ts == datetime.datetime(
            2026, 3, 14, 9, 0, tzinfo=datetime.UTC
        )

    async def test_only_messages_without_time_change_nothing(self) -> None:
        self._serve_pages(_message("untimed"))

        await self.handler.check_for_new_messages()

        assert self._notified() == []
        assert self.handler.last_message_id is None
        assert self.handler.last_message_ts == datetime.datetime.min.replace(
            tzinfo=datetime.UTC
        )
        # The message is still read and, being a vehicle start, deleted
        self.saicapi.read_message.assert_awaited_once_with(message_id="untimed")
        self.saicapi.delete_message.assert_awaited_once_with(message_id="untimed")

    async def test_message_without_time_does_not_stop_paging(self) -> None:
        self.handler.last_message_ts = datetime.datetime(
            2026, 3, 14, 9, 0, tzinfo=datetime.UTC
        )
        newer = _message("newer", "2026-03-14 12:00:00")
        older = _message("older", "2026-03-14 08:00:00")
        never_fetched = _message("never", "2026-03-14 07:00:00")
        self._serve_pages(_message("untimed"), newer, older, never_fetched)

        await self.handler.check_for_new_messages()

        # Paging stops at the first message older than last_message_ts
        assert self.saicapi.get_alarm_list.await_count == 3
        assert self._notified() == [newer]
        assert self.handler.last_message_ts == datetime.datetime(
            2026, 3, 14, 11, 0, tzinfo=datetime.UTC
        )

    async def test_custom_message_timezone(self) -> None:
        self.handler = MessageHandler(
            gateway=self.gateway,
            relogin_handler=self.relogin_handler,
            saicapi=self.saicapi,
            message_timezone=ZoneInfo("Australia/Sydney"),
        )
        self._serve_pages(_message("m1", "2026-07-15 10:00:00"))

        await self.handler.check_for_new_messages()

        assert self.handler.last_message_ts == datetime.datetime(
            2026, 7, 15, 0, 0, tzinfo=datetime.UTC
        )
