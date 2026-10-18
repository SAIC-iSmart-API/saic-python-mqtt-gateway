from __future__ import annotations

import asyncio
import gc
import logging
import unittest

import pytest

from background_tasks import BackgroundTasks


class TestBackgroundTasks(unittest.IsolatedAsyncioTestCase):
    async def test_task_is_held_until_done_then_released(self) -> None:
        tasks = BackgroundTasks()
        release = asyncio.Event()

        async def work() -> str:
            await release.wait()
            return "done"

        task = tasks.spawn(work())
        assert len(tasks) == 1
        release.set()
        assert await task == "done"
        await asyncio.sleep(0)
        assert len(tasks) == 0

    async def test_task_survives_garbage_collection(self) -> None:
        tasks = BackgroundTasks()
        finished = asyncio.Event()

        async def work() -> None:
            await asyncio.sleep(0.01)
            finished.set()

        tasks.spawn(work())
        gc.collect()
        await asyncio.wait_for(finished.wait(), 1)

    async def test_failure_is_logged_and_task_released(self) -> None:
        tasks = BackgroundTasks()

        async def boom() -> None:
            msg = "kaput"
            raise ValueError(msg)

        with self.assertLogs("background_tasks", level=logging.ERROR) as logs:
            task = tasks.spawn(boom(), name="boom-task")
            await asyncio.wait([task])
            await asyncio.sleep(0)

        assert "boom-task" in logs.output[0]
        assert len(tasks) == 0

    async def test_cancelled_task_is_released_without_error_log(self) -> None:
        tasks = BackgroundTasks()
        task = tasks.spawn(asyncio.sleep(10))
        task.cancel()
        with self.assertNoLogs("background_tasks", level=logging.ERROR):
            await asyncio.wait([task])
            await asyncio.sleep(0)
        assert len(tasks) == 0

    async def test_spawn_outside_event_loop_raises(self) -> None:
        tasks = BackgroundTasks()

        async def work() -> None:
            return None

        with pytest.raises(RuntimeError, match="outside the event loop thread"):
            await asyncio.to_thread(lambda: tasks.spawn(work()))
