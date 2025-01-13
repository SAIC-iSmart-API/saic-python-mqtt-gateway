import logging
import logging.config
import os
from typing import Optional

MODULES_DEFAULT_LOG_LEVEL = {
    'httpx': 'WARNING',
    'gmqtt': 'WARNING',
    'saic_ismart_client_ng': 'WARNING',
}

MODULES_REPLACE_ENV_PREFIX = {
    'gmqtt': 'MQTT'
}


def get_default_log_level():
    return os.getenv('LOG_LEVEL', 'INFO').upper()


def debug_log_enabled():
    return get_default_log_level() == 'DEBUG'


# Function to fetch module-specific log levels from environment
def get_module_log_level(module_name: str) -> Optional[str]:
    default_log_level = MODULES_DEFAULT_LOG_LEVEL.get(module_name, None)
    env_prefix = MODULES_REPLACE_ENV_PREFIX.get(module_name, module_name.upper().replace('.', '_'))
    return os.getenv(f'{env_prefix}_LOG_LEVEL', default_log_level)

def setup_logging():
    logger = logging.getLogger(__name__)
    # Read the default log level from the environment
    default_log_level = get_default_log_level()

    logging_config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': '%(asctime)s [%(levelname)s]: %(message)s - %(name)s',
            },
        },
        'handlers': {
            'console': {
                'level': 'DEBUG',
                'class': 'logging.StreamHandler',
                'formatter': 'standard',
            },
        },
        # Catch-all logger with a default level
        'loggers': {},
        'root': {
            'handlers': ['console'],
            'level': default_log_level,
        },
    }

    # Dynamically add loggers based on modules loaded
    loaded_modules = list(logging.Logger.manager.loggerDict.keys())
    logger.debug('Loaded modules:', loaded_modules)
    for module_name in loaded_modules:
        module_log_level = get_module_log_level(
            module_name
        )

        if module_log_level is not None:
            logger.debug("Loaded module {} log level: {}".format(module_name, module_log_level))
            logging_config['loggers'][module_name] = {
                'level': module_log_level.upper(),
                'propagate': True,
            }

    # Apply the logging configuration
    logging.config.dictConfig(logging_config)
