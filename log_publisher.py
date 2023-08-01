import logging

from configuration import Configuration
from publisher import Publisher

LOG = logging.getLogger(__name__)
LOG.setLevel(level="DEBUG")


class Logger(Publisher):
    def __init__(self, configuration: Configuration):
        super().__init__(configuration)

    def publish_json(self, key: str, data: dict, no_prefix: bool = False) -> None:
        LOG.debug(f'{key}: {self.dict_to_anonymized_json(data)}')

    def publish_str(self, key: str, value: str, no_prefix: bool = False) -> None:
        LOG.debug(f'{key}: {value}')

    def publish_int(self, key: str, value: int, no_prefix: bool = False) -> None:
        LOG.debug(f'{key}: {value}')

    def publish_bool(self, key: str, value: bool, no_prefix: bool = False) -> None:
        LOG.debug(f'{key}: {value}')

    def publish_float(self, key: str, value: float, no_prefix: bool = False) -> None:
        LOG.debug(f'{key}: {value}')
