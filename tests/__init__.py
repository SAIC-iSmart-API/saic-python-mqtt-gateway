import logging
from typing import override

from configuration import Configuration
from publisher.log_publisher import ConsolePublisher

LOG = logging.getLogger(__name__)


class MessageCapturingConsolePublisher(ConsolePublisher):
    def __init__(self, configuration: Configuration):
        super().__init__(configuration)
        self.map = {}

    @override
    def internal_publish(self, key, value):
        self.map[key] = value
        LOG.debug(f'{key}: {value}')
