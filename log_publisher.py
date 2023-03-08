import logging

from saicapi.common_model import Configuration
from saicapi.publisher import Publisher


class Logger(Publisher):
    def __init__(self, configuration: Configuration):
        super().__init__(configuration)
        logging.basicConfig(format='%(asctime)s %(message)s', level=logging.DEBUG)

    def publish_json(self, key: str, data: dict, no_prefix: bool = False) -> None:
        logging.debug(f'{key}: {self.dict_to_anonymized_json(data)}')

    def publish_str(self, key: str, value: str, no_prefix: bool = False) -> None:
        logging.debug(f'{key}: {value}')

    def publish_int(self, key: str, value: int, no_prefix: bool = False) -> None:
        logging.debug(f'{key}: {value}')

    def publish_bool(self, key: str, value: bool, no_prefix: bool = False) -> None:
        logging.debug(f'{key}: {value}')

    def publish_float(self, key: str, value: float, no_prefix: bool = False) -> None:
        logging.debug(f'{key}: {value}')
