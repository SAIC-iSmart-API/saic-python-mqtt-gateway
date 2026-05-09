from __future__ import annotations

import json
from typing import Any
import unittest
from unittest.mock import patch

from saic_ismart_client_ng.api.message import MessageEntity
from saic_ismart_client_ng.api.vehicle.schema import VinInfo

from configuration import Configuration
import mqtt_topics
from status_publisher.message import MessagePublisher
from tests.mocks import MessageCapturingConsolePublisher
from vehicle_info import VehicleInfo

VIN = "vin_test_000000000"
VEHICLE_PREFIX = f"vehicles/{VIN}"
EVENT_TOPIC = f"{VEHICLE_PREFIX}/{mqtt_topics.EVENTS_VEHICLE_MESSAGE}"


def _make_publisher() -> tuple[MessagePublisher, MessageCapturingConsolePublisher]:
    config = Configuration()
    config.anonymized_publishing = False
    capturing_publisher = MessageCapturingConsolePublisher(config)
    vin_info = VinInfo()
    vin_info.vin = VIN
    vehicle_info = VehicleInfo(vin_info, None)
    msg_publisher = MessagePublisher(vehicle_info, capturing_publisher, VEHICLE_PREFIX)
    return msg_publisher, capturing_publisher


def _make_message(
    *,
    message_id: str = "msg_001",
    title: str = "Test Alert",
    content: str = "Your vehicle has been started",
    message_type: str = "323",
    sender: str = "iSMART",
    vin: str = VIN,
    message_time: str = "2026-03-14 10:00:00",
) -> MessageEntity:
    return MessageEntity(
        messageId=message_id,
        title=title,
        content=content,
        messageType=message_type,
        sender=sender,
        vin=vin,
        messageTime=message_time,
    )


def _get_event(capturing: MessageCapturingConsolePublisher) -> dict[str, Any]:
    raw = capturing.map[EVENT_TOPIC]
    result: dict[str, Any] = json.loads(raw)
    return result


class TestMessageEventPublished(unittest.TestCase):
    def test_new_message_publishes_event(self) -> None:
        publisher, capturing = _make_publisher()

        result = publisher.publish(_make_message())

        assert result.processed is True
        assert EVENT_TOPIC in capturing.map
        event = _get_event(capturing)
        assert event["event_type"] == "vehicle_message"
        assert event["title"] == "Test Alert"
        assert event["content"] == "Your vehicle has been started"
        assert event["message_type"] == "323"
        assert event["sender"] == "iSMART"
        assert event["vin"] == VIN

    def test_duplicate_message_not_published(self) -> None:
        publisher, capturing = _make_publisher()
        msg = _make_message()

        publisher.publish(msg)
        capturing.map.clear()

        result = publisher.publish(msg)

        assert result.processed is False
        assert EVENT_TOPIC not in capturing.map

    def test_newer_message_publishes_event(self) -> None:
        publisher, capturing = _make_publisher()

        publisher.publish(_make_message(message_time="2026-03-14 10:00:00"))
        capturing.map.clear()

        result = publisher.publish(
            _make_message(
                message_id="msg_002",
                title="Second Alert",
                message_time="2026-03-14 11:00:00",
            )
        )

        assert result.processed is True
        event = _get_event(capturing)
        assert event["title"] == "Second Alert"

    def test_older_message_not_published(self) -> None:
        publisher, capturing = _make_publisher()

        publisher.publish(_make_message(message_time="2026-03-14 10:00:00"))
        capturing.map.clear()

        result = publisher.publish(
            _make_message(
                message_id="msg_old",
                message_time="2026-03-14 09:00:00",
            )
        )

        assert result.processed is False
        assert EVENT_TOPIC not in capturing.map


class TestMessageEventPayload(unittest.TestCase):
    def test_none_fields_become_empty_strings(self) -> None:
        publisher, capturing = _make_publisher()

        msg = MessageEntity(
            messageId="msg_none",
            messageTime="2026-03-14 10:00:00",
        )
        publisher.publish(msg)

        event = _get_event(capturing)
        assert event["title"] == ""
        assert event["content"] == ""
        assert event["message_type"] == ""
        assert event["sender"] == ""
        assert event["vin"] == ""

    def test_event_payload_keys(self) -> None:
        publisher, capturing = _make_publisher()

        publisher.publish(_make_message())

        event = _get_event(capturing)
        assert set(event.keys()) == {
            "event_type",
            "title",
            "content",
            "message_type",
            "sender",
            "vin",
        }


class TestMessageEventResilience(unittest.TestCase):
    def test_event_publish_failure_does_not_break_processing(self) -> None:
        publisher, capturing = _make_publisher()
        original_publish = capturing.publish

        def failing_publish(
            key: str,
            value: Any,
            no_prefix: bool = False,
            *,
            retain: bool = True,
        ) -> None:
            if mqtt_topics.EVENTS_VEHICLE_MESSAGE in key:
                raise RuntimeError("MQTT down")
            original_publish(key, value, no_prefix, retain=retain)

        with patch.object(capturing, "publish", side_effect=failing_publish):
            result = publisher.publish(_make_message())

        assert result.processed is True
        assert EVENT_TOPIC not in capturing.map
        time_topic = f"{VEHICLE_PREFIX}/{mqtt_topics.INFO_LAST_MESSAGE_TIME}"
        assert time_topic in capturing.map
