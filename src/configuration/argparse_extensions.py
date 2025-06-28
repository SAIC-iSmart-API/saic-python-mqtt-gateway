from __future__ import annotations

import argparse
from argparse import ArgumentParser, Namespace
from gettext import gettext as _
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, override

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


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
            # append environment variables
            if action.envvar:
                _help += f"\n(environment variable: {action.envvar})"
            if action.file_envvar:
                _help += f"\n(file environment variable: {action.file_envvar})"
        # whitespace from each line
        return "\n".join([m.lstrip() for m in _help.split("\n")])


class EnvDefault(argparse.Action):
    """Argparse action that allows setting a default from environment variable or file."""

    def __init__(
        self,
        envvar: str,
        required: bool = True,
        try_file: bool = False,
        default: str | None = None,
        **kwargs: dict[str, Any],
    ) -> None:
        self.envvar = envvar
        self.file_envvar = f"{envvar}_FILE" if try_file else None

        envvar_value = os.environ.get(self.envvar, None)
        envvar_file_value = (
            os.environ.get(self.file_envvar, None) if self.file_envvar else None
        )

        if envvar_value is not None:
            # enviroment value takes precedence
            default = envvar_value
        elif envvar_file_value:
            # if the environment variable is not set, check for a file specified by the environment variable with the _FILE suffix
            default_from_file = self._get_default_from_file(envvar_file_value)
            if default_from_file:
                default = default_from_file

        if required and default:
            # If the default is set from environment, it should not be required from command line
            required = False
        super().__init__(required=required, default=default, **kwargs)

    def _get_default_from_file(self, file_path: str) -> str | None:
        """Get the default value from the file specified by the environment variable."""
        try:
            with Path(file_path).open(encoding="utf-8") as f:
                return f.read().strip()
        except OSError as e:
            msg = f"Error reading file {file_path}, specified by environment variable {self.file_envvar}"
            raise argparse.ArgumentTypeError(msg) from e

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
