from __future__ import annotations

import argparse
from argparse import ArgumentParser, Namespace
import os
from typing import TYPE_CHECKING, Any, override

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


class EnvDefault(argparse.Action):
    def __init__(
        self,
        envvar: str,
        required: bool = True,
        default: str | None = None,
        **kwargs: dict[str, Any],
    ) -> None:
        if os.environ.get(envvar):
            default = os.environ[envvar]
        if required and default:
            required = False
        super().__init__(default=default, required=required, **kwargs)

    @override
    def __call__(
        self,
        parser: ArgumentParser,
        namespace: Namespace,
        values: str | Sequence[str] | None,
        option_string: str | None = None,
    ) -> None:
        setattr(namespace, self.dest, values)


def cfg_value_to_dict(
    cfg_value: str, result_map: dict[str, Any], value_type: Callable[[str], Any] = str
) -> None:
    map_entries = cfg_value.split(",") if "," in cfg_value else [cfg_value]

    for entry in map_entries:
        if "=" in entry:
            key_value_pair = entry.split("=")
            key = key_value_pair[0]
            value = key_value_pair[1]
            result_map[key] = value_type(value)


def check_positive(value: str) -> int:
    ivalue = int(value)
    if ivalue <= 0:
        msg = f"{ivalue} is an invalid positive int value"
        raise argparse.ArgumentTypeError(msg)
    return ivalue


def check_positive_float(value: str) -> float:
    fvalue = float(value)
    if fvalue <= 0:
        msg = f"{fvalue} is an invalid positive float value"
        raise argparse.ArgumentTypeError(msg)
    return fvalue


def check_bool(value: str) -> bool:
    return str(value).lower() in ["true", "1", "yes", "y"]
