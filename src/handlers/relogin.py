from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from saic_ismart_client_ng import SaicApi

LOG = logging.getLogger(__name__)
JOB_ID = "relogin_task"


class ReloginHandler:
    def __init__(
        self, *, relogin_relay: int, api: SaicApi, scheduler: AsyncIOScheduler
    ) -> None:
        self.__relogin_relay = relogin_relay
        self.__scheduler = scheduler
        self.__api = api
        self.__login_task = None

    @property
    def relogin_in_progress(self) -> bool:
        return self.__login_task is not None

    def relogin(self) -> None:
        if self.__login_task is None:
            LOG.warning(
                f"API Client got logged out, logging back in {self.__relogin_relay} seconds"
            )
            self.__login_task = self.__scheduler.add_job(
                func=self.login,
                trigger="date",
                run_date=datetime.now() + timedelta(seconds=self.__relogin_relay),
                id=JOB_ID,
                name="Re-login the API client after a set delay",
                max_instances=1,
            )

    async def login(self) -> None:
        try:
            LOG.info("Logging in to SAIC API")
            login_response_message = await self.__api.login()
            LOG.info("Logged in as %s", login_response_message.account)
        except Exception as e:
            LOG.exception("Could not login to the SAIC API due to an error", exc_info=e)
            raise e
        finally:
            if self.__scheduler.get_job(JOB_ID) is not None:
                self.__scheduler.remove_job(JOB_ID)
            self.__login_task = None
