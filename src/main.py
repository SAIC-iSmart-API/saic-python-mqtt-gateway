from __future__ import annotations

import asyncio
import faulthandler
import signal
import sys

from configuration.parser import process_arguments
from mqtt_gateway import MqttGateway

if __name__ == "__main__":
    # Keep this at the top!
    from log_config import debug_log_enabled, setup_logging

    setup_logging()

    # Enable fault handler to get a thread dump on SIGQUIT
    faulthandler.enable(file=sys.stderr, all_threads=True)
    if hasattr(faulthandler, "register") and hasattr(signal, "SIGQUIT"):
        faulthandler.register(signal.SIGQUIT, chain=False)
    configuration = process_arguments()

    mqtt_gateway = MqttGateway(configuration)
    asyncio.run(mqtt_gateway.run(), debug=debug_log_enabled())
