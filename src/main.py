from __future__ import annotations

import asyncio
import faulthandler
import logging
import signal
import sys

from configuration.parser import process_command_line
from mqtt_gateway import MqttGateway
from shutdown import run_until_terminated
from utils import get_gateway_version

if __name__ == "__main__":
    # Keep this at the top!
    from log_config import debug_log_enabled, setup_logging

    setup_logging()
    log = logging.getLogger(__name__)
    log.info(f"Starting SAIC MQTT Gateway version {get_gateway_version()}")

    # Enable fault handler to get a thread dump on SIGQUIT
    faulthandler.enable(file=sys.stderr, all_threads=True)
    if hasattr(faulthandler, "register") and hasattr(signal, "SIGQUIT"):
        faulthandler.register(signal.SIGQUIT, chain=False)
    configuration = process_command_line()

    mqtt_gateway = MqttGateway(configuration)

    asyncio.run(run_until_terminated(mqtt_gateway.run()), debug=debug_log_enabled())
