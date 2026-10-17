from __future__ import annotations

import asyncio
import os
import signal
import sys
import unittest

import pytest

from shutdown import run_until_terminated


@pytest.mark.skipif(sys.platform == "win32", reason="needs POSIX signals")
class TestRunUntilTerminated(unittest.IsolatedAsyncioTestCase):
    async def test_sigterm_cancels_main_and_runs_cleanup(self) -> None:
        cleaned_up = False

        async def main() -> None:
            nonlocal cleaned_up
            try:
                await asyncio.sleep(30)
            finally:
                cleaned_up = True

        loop = asyncio.get_running_loop()
        loop.call_later(0.05, os.kill, os.getpid(), signal.SIGTERM)

        await run_until_terminated(main())

        assert cleaned_up

    async def test_normal_completion_returns(self) -> None:
        done = False

        async def main() -> None:
            nonlocal done
            done = True

        await run_until_terminated(main())

        assert done

    async def test_exceptions_from_main_propagate(self) -> None:
        async def main() -> None:
            msg = "boom"
            raise RuntimeError(msg)

        with pytest.raises(RuntimeError):
            await run_until_terminated(main())

    async def test_external_cancellation_is_not_swallowed(self) -> None:
        async def main() -> None:
            await asyncio.sleep(30)

        runner = asyncio.ensure_future(run_until_terminated(main()))
        await asyncio.sleep(0.05)
        runner.cancel()

        with pytest.raises(asyncio.CancelledError):
            await runner

    async def test_sigterm_handler_removed_afterwards(self) -> None:
        async def main() -> None:
            return None

        await run_until_terminated(main())

        assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL
