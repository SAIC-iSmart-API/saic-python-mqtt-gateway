from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Coroutine

LOG = logging.getLogger(__name__)


def log_task_failure(task: asyncio.Task[Any]) -> None:
    """Log the exception of a finished ``task``, if any.

    Meant as a done-callback, so that a failure is reported when it happens
    instead of when the task is garbage collected.
    """
    if not task.cancelled() and (exc := task.exception()) is not None:
        LOG.error("Background task %r failed", task.get_name(), exc_info=exc)


class BackgroundTasks:
    """Fire-and-forget tasks that are kept alive and whose failures are logged.

    asyncio only keeps weak references to tasks, so a task nobody references can
    be garbage collected mid-run. An exception nobody retrieves is only reported
    when the task is collected. ``spawn`` takes care of both.
    """

    def __init__(self) -> None:
        self.__tasks: set[asyncio.Task[Any]] = set()

    def __len__(self) -> int:
        return len(self.__tasks)

    def spawn(
        self, coro: Coroutine[Any, Any, Any], *, name: str | None = None
    ) -> asyncio.Task[Any]:
        """Run ``coro`` on the running event loop.

        Raises ``RuntimeError`` when called outside of the event loop thread.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as e:
            what = name or getattr(coro, "__qualname__", repr(coro))
            coro.close()
            msg = (
                f"Cannot start background task {what!r} outside the event loop "
                "thread. Run it from a coroutine, e.g. register scheduler jobs as "
                "async functions"
            )
            raise RuntimeError(msg) from e
        task = loop.create_task(coro, name=name)
        self.__tasks.add(task)
        task.add_done_callback(self.__on_done)
        return task

    async def wait(self) -> None:
        """Wait until the tasks running right now are done.

        Tasks are released and failures logged by the time this returns. To bound
        the wait, wrap it in ``asyncio.wait_for``: that does not cancel the tasks.
        """
        if self.__tasks:
            await asyncio.wait(set(self.__tasks))

    def __on_done(self, task: asyncio.Task[Any]) -> None:
        self.__tasks.discard(task)
        log_task_failure(task)
