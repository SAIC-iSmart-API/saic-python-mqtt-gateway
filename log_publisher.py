import logging

from saicapi.common_model import Configuration
from saicapi.publisher import Publisher


class Logger(Publisher):
    def __init__(self, configuration: Configuration):
        super().__init__(configuration)
        logging.basicConfig(format='%(asctime)s %(message)s', level=logging.DEBUG)

    def publish_json(self, key: str, data: dict) -> None:
        logging.debug(f'{key}: {self.dict_to_anonymized_json(data)}')

    def publish_str(self, key: str, value: str) -> None:
        logging.debug(f'{key}: {value}')

    def publish_int(self, key: str, value: int) -> None:
        logging.debug(f'{key}: {value}')

    def publish_bool(self, key: str, value: bool) -> None:
        logging.debug(f'{key}: {value}')

    def publish_float(self, key: str, value: float) -> None:
        logging.debug(f'{key}: {value}')
