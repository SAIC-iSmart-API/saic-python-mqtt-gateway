from __future__ import annotations

import logging
import re

import inflection

LOG = logging.getLogger(__name__)


def snake_case(s: str) -> str:
    return inflection.underscore(s.lower()).replace(" ", "_")


def gateway_device_id(account_prefix: str) -> str:
    """Home Assistant identifier of the gateway device for an account."""
    return re.sub(r"[^a-z0-9_]", "_", snake_case(account_prefix))


def decode_as_utf8(
    byte_string: str | bytes | bytearray | None, default: str = ""
) -> str:
    if byte_string is None:
        return default
    if isinstance(byte_string, str):
        return byte_string
    if isinstance(byte_string, bytes | bytearray):
        try:
            return str(byte_string, encoding="utf8", errors="ignore")
        except Exception:
            LOG.exception(f"Failed to decode {byte_string!r} as utf8")
            return default
    else:
        try:  # type: ignore[unreachable]
            return str(byte_string)
        except Exception:
            LOG.exception(f"Failed to decode {byte_string}")
            return default
