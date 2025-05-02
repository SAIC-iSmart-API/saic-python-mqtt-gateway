from __future__ import annotations

import logging
import logging.config
import os
from typing import Any

MODULES_DEFAULT_LOG_LEVEL = {
    "asyncio": "WARNING",
    "gmqtt": "WARNING",
    "httpcore": "WARNING",
    "httpx": "WARNING",
    "saic_ismart_client_ng": "WARNING",
    "tzlocal": "WARNING",
}

MODULES_REPLACE_ENV_PREFIX = {"gmqtt": "MQTT"}


def get_default_log_level() -> str:
    return os.getenv("LOG_LEVEL", "INFO").upper()


def debug_log_enabled() -> bool:
    return get_default_log_level() == "DEBUG"


# Function to fetch module-specific log levels from environment
def get_module_log_level(module_name: str) -> str | None:
    default_log_level = MODULES_DEFAULT_LOG_LEVEL.get(module_name)
    env_prefix = MODULES_REPLACE_ENV_PREFIX.get(
        module_name, module_name.upper().replace(".", "_")
    )
    return os.getenv(f"{env_prefix}_LOG_LEVEL", default_log_level)


def setup_logging() -> None:
    logger = logging.getLogger(__name__)
    # Read the default log level from the environment
    default_log_level = get_default_log_level()

    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s [%(levelname)s]: %(message)s - %(name)s",
            },
        },
        "handlers": {
            "console": {
                "level": "DEBUG",
                "class": "logging.StreamHandler",
                "formatter": "standard",
            },
        },
        # Catch-all logger with a default level
        "root": {
            "handlers": ["console"],
            "level": default_log_level,
        },
    }

    # Dynamically add loggers based on modules loaded
    loaded_modules = list(logging.Logger.manager.loggerDict.keys())
    logger.debug("Loaded modules: %s", loaded_modules)
    modules_override: dict[str, Any] = {}
    for module_name in loaded_modules:
        module_log_level = get_module_log_level(module_name)

        if module_log_level is not None:
            logger.debug(f"Loaded module {module_name} log level: {module_log_level}")
            modules_override[module_name] = {
                "level": module_log_level.upper(),
                "propagate": True,
            }
    logging_config.update({"loggers": modules_override})

    # Apply the logging configuration
    logging.config.dictConfig(logging_config)
