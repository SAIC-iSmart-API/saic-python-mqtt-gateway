from __future__ import annotations

import argparse
from argparse import ArgumentParser, Namespace
from gettext import gettext as _
import os
from typing import TYPE_CHECKING, Any, override

from dotenv import dotenv_values

from utils import parse_timezone

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from zoneinfo import ZoneInfo


# load .env file and merge with os.environ
merged_environ = {**dotenv_values(".env"), **os.environ}


class ArgumentHelpFormatter(argparse.RawTextHelpFormatter):
    """Custom argument formatter.

    Appends environment variable and default value to help.
    """

    def _get_help_string(self, action: argparse.Action) -> str | None:
        _help = action.help
        if _help is None:
            _help = ""

        if isinstance(action, EnvDefault):
            # append type
            t = action.type
            if t is not None:
                if (
                    hasattr(t, "__annotations__")
                    and t.__annotations__.get("return", None) is not None
                ):
                    _help += f"\n(type: {t.__annotations__.get('return', None)})"
                elif hasattr(t, "__name__"):
                    _help += f"\n(type: {t.__name__})"

            if "%(default)" not in _help and action.default is not argparse.SUPPRESS:
                defaulting_nargs = [argparse.OPTIONAL, argparse.ZERO_OR_MORE]
                if action.option_strings or action.nargs in defaulting_nargs:
                    # append default value
                    _help += _("\n(default: %(default)s)")
            # append environment variable
            _help += f"\n(environment variable: {action.envvar})"
        # strip whitespace from each line
        return "\n".join([m.lstrip() for m in _help.split("\n")])


class EnvDefault(argparse.Action):
    def __init__(
        self,
        envvar: str,
        required: bool = True,
        default: str | None = None,
        **kwargs: dict[str, Any],
    ) -> None:
        self.envvar = envvar
        if merged_environ.get(envvar):
            default = merged_environ[envvar]
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
            key, value = entry.split("=", maxsplit=1)
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


def check_timezone(value: str) -> ZoneInfo:
    try:
        return parse_timezone(value)
    except (ValueError, KeyError, ModuleNotFoundError) as e:
        msg = f"{value!r} is not a valid timezone"
        raise argparse.ArgumentTypeError(msg) from e
