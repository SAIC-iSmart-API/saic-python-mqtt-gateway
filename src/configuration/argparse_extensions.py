import argparse
import os
from typing import Callable


class EnvDefault(argparse.Action):
    def __init__(self, envvar, required=True, default=None, **kwargs):
        if (
                envvar in os.environ
                and os.environ[envvar]
        ):
            default = os.environ[envvar]
        if required and default:
            required = False
        super(EnvDefault, self).__init__(default=default, required=required, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)


def cfg_value_to_dict(cfg_value: str, result_map: dict, value_type: Callable[[str], any] = str):
    if ',' in cfg_value:
        map_entries = cfg_value.split(',')
    else:
        map_entries = [cfg_value]

    for entry in map_entries:
        if '=' in entry:
            key_value_pair = entry.split('=')
            key = key_value_pair[0]
            value = key_value_pair[1]
            result_map[key] = value_type(value)


def check_positive(value):
    ivalue = int(value)
    if ivalue <= 0:
        raise argparse.ArgumentTypeError(f'{ivalue} is an invalid positive int value')
    return ivalue


def check_positive_float(value):
    fvalue = float(value)
    if fvalue <= 0:
        raise argparse.ArgumentTypeError(f'{fvalue} is an invalid positive float value')
    return fvalue


def check_bool(value):
    return str(value).lower() in ['true', '1', 'yes', 'y']
