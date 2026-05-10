"""Conformance tests for `Publisher.publish` dispatch across all subclasses.

`Publisher.publish` is a single non-abstract method on the ABC that dispatches
based on the runtime type of `value` to the corresponding typed
`publish_{bool,int,float,str,datetime,json}` method. `publish_datetime` is itself
a concrete ABC-level method that stringifies via :func:`utils.datetime_to_str`
and forwards to `publish_str`. The tests below exercise that dispatch directly
on every concrete `Publisher` subclass shipped by the project, plus a minimal
in-test subclass that locks the contract at the ABC level.

The critical regression these tests guard against: `bool` is a subclass of
`int` in Python, so `isinstance(True, int)` is `True`. The dispatch must check
`bool` *before* `int` so that `publish(key, True)` reaches `publish_bool` (not
`publish_int`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, override
from unittest.mock import MagicMock, patch

import pytest

from configuration import Configuration, TransportProtocol
from publisher.core import Publishable, Publisher
from publisher.log_publisher import ConsolePublisher
from publisher.mqtt_publisher import MqttPublisher
from tests.mocks import MessageCapturingConsolePublisher
from utils import datetime_to_str

if TYPE_CHECKING:
    from collections.abc import Callable


KEY = "some/topic"


def _make_configuration() -> Configuration:
    config = Configuration()
    config.mqtt_topic = "saic"
    config.saic_user = "user@example.com"
    config.mqtt_transport_protocol = TransportProtocol.TCP
    return config


# Each entry: (label, factory) where factory returns a fresh concrete Publisher.
PUBLISHER_FACTORIES: list[tuple[str, Callable[[], Publisher]]] = [
    ("MqttPublisher", lambda: MqttPublisher(_make_configuration())),
    ("ConsolePublisher", lambda: ConsolePublisher(_make_configuration())),
    (
        "MessageCapturingConsolePublisher",
        lambda: MessageCapturingConsolePublisher(_make_configuration()),
    ),
]


# (label, value, expected typed-method name) for arms where the value is
# forwarded to the typed method unchanged.
PASSTHROUGH_CASES: list[tuple[str, Publishable, str]] = [
    ("bool_true", True, "publish_bool"),
    ("bool_false", False, "publish_bool"),
    ("int_value", 5, "publish_int"),
    ("int_zero", 0, "publish_int"),
    ("float_value", 5.0, "publish_float"),
    ("str_value", "hi", "publish_str"),
    (
        "datetime_value",
        datetime(2026, 5, 9, 12, 34, 56, tzinfo=UTC),
        "publish_datetime",
    ),
]

TYPED_METHODS = (
    "publish_bool",
    "publish_int",
    "publish_float",
    "publish_str",
    "publish_datetime",
    "publish_json",
)


@pytest.mark.parametrize(
    ("publisher_label", "factory"),
    PUBLISHER_FACTORIES,
    ids=[label for label, _ in PUBLISHER_FACTORIES],
)
@pytest.mark.parametrize(
    ("case_label", "value", "expected_method"),
    PASSTHROUGH_CASES,
    ids=[label for label, _, _ in PASSTHROUGH_CASES],
)
def test_publish_dispatches_to_correct_typed_method(
    publisher_label: str,
    factory: Callable[[], Publisher],
    case_label: str,
    value: Publishable,
    expected_method: str,
) -> None:
    del publisher_label, case_label  # only used as test ids
    publisher = factory()
    with (
        patch.object(publisher, "publish_bool") as m_bool,
        patch.object(publisher, "publish_int") as m_int,
        patch.object(publisher, "publish_float") as m_float,
        patch.object(publisher, "publish_str") as m_str,
        patch.object(publisher, "publish_datetime") as m_dt,
        patch.object(publisher, "publish_json") as m_json,
    ):
        spies = {
            "publish_bool": m_bool,
            "publish_int": m_int,
            "publish_float": m_float,
            "publish_str": m_str,
            "publish_datetime": m_dt,
            "publish_json": m_json,
        }
        publisher.publish(KEY, value)

        spies[expected_method].assert_called_once_with(KEY, value, False, retain=True)
        for name in TYPED_METHODS:
            if name != expected_method:
                spies[name].assert_not_called()


@pytest.mark.parametrize(
    ("publisher_label", "factory"),
    PUBLISHER_FACTORIES,
    ids=[label for label, _ in PUBLISHER_FACTORIES],
)
def test_publish_dict_routes_to_publish_json_with_retain(
    publisher_label: str,
    factory: Callable[[], Publisher],
) -> None:
    """`dict` values dispatch to `publish_json`, forwarding `retain`."""
    del publisher_label
    publisher = factory()
    payload: dict[str, Any] = {"a": 1, "b": "two"}
    with patch.object(publisher, "publish_json") as m_json:
        publisher.publish(KEY, payload, retain=False)
        m_json.assert_called_once_with(KEY, payload, False, retain=False)


@pytest.mark.parametrize(
    ("publisher_label", "factory"),
    PUBLISHER_FACTORIES,
    ids=[label for label, _ in PUBLISHER_FACTORIES],
)
@pytest.mark.parametrize(
    ("case_label", "value", "expected_method"),
    PASSTHROUGH_CASES,
    ids=[label for label, _, _ in PASSTHROUGH_CASES],
)
def test_publish_forwards_retain_false_to_every_arm(
    publisher_label: str,
    factory: Callable[[], Publisher],
    case_label: str,
    value: Publishable,
    expected_method: str,
) -> None:
    """`retain=False` reaches every typed dispatch target, not just `publish_json`."""
    del publisher_label, case_label
    publisher = factory()
    with patch.object(publisher, expected_method) as m:
        publisher.publish(KEY, value, retain=False)
        m.assert_called_once_with(KEY, value, False, retain=False)


@pytest.mark.parametrize(
    ("publisher_label", "factory"),
    PUBLISHER_FACTORIES,
    ids=[label for label, _ in PUBLISHER_FACTORIES],
)
def test_publish_datetime_stringifies_via_publish_str(
    publisher_label: str,
    factory: Callable[[], Publisher],
) -> None:
    """`publish_datetime` stringifies via `datetime_to_str` and forwards to `publish_str`."""
    del publisher_label
    publisher = factory()
    when = datetime(2026, 5, 9, 12, 34, 56, tzinfo=UTC)
    with patch.object(publisher, "publish_str") as m_str:
        publisher.publish_datetime(KEY, when)
        m_str.assert_called_once_with(KEY, datetime_to_str(when), False, retain=True)


@pytest.mark.parametrize(
    ("publisher_label", "factory"),
    PUBLISHER_FACTORIES,
    ids=[label for label, _ in PUBLISHER_FACTORIES],
)
def test_publish_forwards_no_prefix_flag(
    publisher_label: str,
    factory: Callable[[], Publisher],
) -> None:
    del publisher_label
    publisher = factory()
    with patch.object(publisher, "publish_str") as m_str:
        publisher.publish(KEY, "hello", no_prefix=True)
        m_str.assert_called_once_with(KEY, "hello", True, retain=True)


@pytest.mark.parametrize(
    ("publisher_label", "factory"),
    PUBLISHER_FACTORIES,
    ids=[label for label, _ in PUBLISHER_FACTORIES],
)
def test_publish_true_routes_to_bool_not_int(
    publisher_label: str,
    factory: Callable[[], Publisher],
) -> None:
    """Locks in the bool-before-int dispatch ordering.

    `isinstance(True, int)` is `True` in Python, so a naive `int` check first
    would silently route `True`/`False` to `publish_int`.
    """
    del publisher_label
    publisher = factory()
    with (
        patch.object(publisher, "publish_bool") as m_bool,
        patch.object(publisher, "publish_int") as m_int,
    ):
        publisher.publish(KEY, True)
        m_bool.assert_called_once_with(KEY, True, False, retain=True)
        m_int.assert_not_called()


@pytest.mark.parametrize(
    ("publisher_label", "factory"),
    PUBLISHER_FACTORIES,
    ids=[label for label, _ in PUBLISHER_FACTORIES],
)
def test_publish_int_does_not_route_to_bool(
    publisher_label: str,
    factory: Callable[[], Publisher],
) -> None:
    del publisher_label
    publisher = factory()
    with (
        patch.object(publisher, "publish_bool") as m_bool,
        patch.object(publisher, "publish_int") as m_int,
    ):
        publisher.publish(KEY, 5)
        m_int.assert_called_once_with(KEY, 5, False, retain=True)
        m_bool.assert_not_called()


@pytest.mark.parametrize(
    ("publisher_label", "factory"),
    PUBLISHER_FACTORIES,
    ids=[label for label, _ in PUBLISHER_FACTORIES],
)
def test_publish_unsupported_type_raises(
    publisher_label: str,
    factory: Callable[[], Publisher],
) -> None:
    """Unsupported runtime types raise rather than silently no-op."""
    del publisher_label
    publisher = factory()
    with pytest.raises(TypeError, match="Unsupported value type"):
        publisher.publish(KEY, b"bytes-not-supported")  # type: ignore[arg-type]


class _MinimalPublisher(Publisher):
    """ABC-level publisher that mocks only the typed publish methods.

    Keeps the dispatch contract pinned even if all concrete subclasses were
    to override `publish` in the future.
    """

    def __init__(self, config: Configuration) -> None:
        super().__init__(config)
        self.publish_bool = MagicMock()  # type: ignore[method-assign]
        self.publish_int = MagicMock()  # type: ignore[method-assign]
        self.publish_float = MagicMock()  # type: ignore[method-assign]
        self.publish_str = MagicMock()  # type: ignore[method-assign]
        self.publish_datetime = MagicMock()  # type: ignore[method-assign]
        self.publish_json = MagicMock()  # type: ignore[method-assign]
        self.clear_topic = MagicMock()  # type: ignore[method-assign]

    @override
    async def connect(self) -> None:
        pass

    @override
    def enable_commands(self) -> None:
        pass

    @override
    def is_connected(self) -> bool:
        return True

    @override
    def publish_json(
        self,
        key: str,
        data: dict[str, Any],
        no_prefix: bool = False,
        *,
        retain: bool = True,
    ) -> None:
        pass

    @override
    def publish_str(
        self, key: str, value: str, no_prefix: bool = False, *, retain: bool = True
    ) -> None:
        pass

    @override
    def publish_int(
        self, key: str, value: int, no_prefix: bool = False, *, retain: bool = True
    ) -> None:
        pass

    @override
    def publish_bool(
        self, key: str, value: bool, no_prefix: bool = False, *, retain: bool = True
    ) -> None:
        pass

    @override
    def publish_float(
        self, key: str, value: float, no_prefix: bool = False, *, retain: bool = True
    ) -> None:
        pass

    @override
    def clear_topic(self, key: str, no_prefix: bool = False) -> None:
        pass


@pytest.mark.parametrize(
    ("case_label", "value", "expected_method"),
    PASSTHROUGH_CASES,
    ids=[label for label, _, _ in PASSTHROUGH_CASES],
)
def test_abc_level_publish_dispatch(
    case_label: str,
    value: Publishable,
    expected_method: str,
) -> None:
    del case_label
    publisher = _MinimalPublisher(_make_configuration())
    publisher.publish(KEY, value)
    spies: dict[str, MagicMock] = {
        "publish_bool": publisher.publish_bool,  # type: ignore[dict-item]
        "publish_int": publisher.publish_int,  # type: ignore[dict-item]
        "publish_float": publisher.publish_float,  # type: ignore[dict-item]
        "publish_str": publisher.publish_str,  # type: ignore[dict-item]
        "publish_datetime": publisher.publish_datetime,  # type: ignore[dict-item]
        "publish_json": publisher.publish_json,  # type: ignore[dict-item]
    }
    spies[expected_method].assert_called_once_with(KEY, value, False, retain=True)
    for name in TYPED_METHODS:
        if name != expected_method:
            spies[name].assert_not_called()


def test_abc_level_publish_dict_with_retain() -> None:
    publisher = _MinimalPublisher(_make_configuration())
    payload: dict[str, Any] = {"x": 1}
    publisher.publish(KEY, payload, retain=False)
    publisher.publish_json.assert_called_once_with(KEY, payload, False, retain=False)  # type: ignore[attr-defined]


def test_abc_level_publish_datetime_routes_to_publish_datetime() -> None:
    publisher = _MinimalPublisher(_make_configuration())
    when = datetime(2026, 5, 9, 12, 34, 56, tzinfo=UTC)
    publisher.publish(KEY, when)
    publisher.publish_datetime.assert_called_once_with(KEY, when, False, retain=True)  # type: ignore[attr-defined]
