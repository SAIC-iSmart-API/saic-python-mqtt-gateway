from __future__ import annotations

import asyncio
import logging
import signal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Coroutine

LOG = logging.getLogger(__name__)


async def run_until_terminated(main: Coroutine[Any, Any, None]) -> None:
    """Run ``main``, cancelling it cleanly when the process receives SIGTERM.

    Python does not handle SIGTERM by default, and as PID 1 in a container it
    would simply ignore it. Cancelling the task lets its ``finally`` blocks run.
    """
    loop = asyncio.get_running_loop()
    task = loop.create_task(main)
    terminated = False

    def request_shutdown() -> None:
        nonlocal terminated
        terminated = True
        LOG.info("Received SIGTERM, shutting down")
        task.cancel()

    handler_installed = False
    try:
        loop.add_signal_handler(signal.SIGTERM, request_shutdown)
        handler_installed = True
    except (NotImplementedError, RuntimeError, ValueError):
        LOG.debug("Cannot install a SIGTERM handler on this platform")

    try:
        await task
    except asyncio.CancelledError:
        if not terminated:
            raise
    finally:
        if handler_installed:
            loop.remove_signal_handler(signal.SIGTERM)
