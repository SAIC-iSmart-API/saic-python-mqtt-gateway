from __future__ import annotations

import datetime
import logging
from unittest import TestCase
from zoneinfo import ZoneInfo

import httpx
import pytest
from saic_ismart_client_ng.api.schema import GpsPosition, GpsStatus
from saic_ismart_client_ng.api.vehicle import VehicleStatusResp
from saic_ismart_client_ng.exceptions import SaicApiException

from utils import (
    get_update_timestamp,
    is_api_timeout,
    log_api_timeout,
    parse_timezone,
)


class Test(TestCase):
    def test_get_update_timestamp_should_return_vehicle_if_closest(self) -> None:
        base_ts = datetime.datetime.now(tz=datetime.UTC)
        ts_plus_30_s = base_ts + datetime.timedelta(minutes=1)
        vehicle_status_resp = VehicleStatusResp(
            statusTime=int(base_ts.timestamp()),
            gpsPosition=GpsPosition(
                gpsStatus=GpsStatus.FIX_3d.value,
                timeStamp=int(ts_plus_30_s.timestamp()),
            ),
        )

        result = get_update_timestamp(vehicle_status_resp)

        assert int(result.timestamp()) == int(base_ts.timestamp()), (
            "This test should have selected the vehicle timestamp"
        )

        assert result <= datetime.datetime.now(tz=datetime.UTC)

    def test_get_update_timestamp_should_return_gps_if_closest(self) -> None:
        base_ts = datetime.datetime.now(tz=datetime.UTC)
        ts_plus_30_s = base_ts + datetime.timedelta(minutes=1)
        vehicle_status_resp = VehicleStatusResp(
            statusTime=int(ts_plus_30_s.timestamp()),
            gpsPosition=GpsPosition(
                gpsStatus=GpsStatus.FIX_3d.value,
                timeStamp=int(base_ts.timestamp()),
            ),
        )

        result = get_update_timestamp(vehicle_status_resp)

        assert int(result.timestamp()) == int(base_ts.timestamp()), (
            "This test should have selected the GPS timestamp"
        )

        assert result <= datetime.datetime.now(tz=datetime.UTC)

    def test_get_update_timestamp_should_return_now_if_drift_too_much(self) -> None:
        base_ts = datetime.datetime.now(tz=datetime.UTC) + datetime.timedelta(
            minutes=30
        )
        ts_plus_30_s = base_ts + datetime.timedelta(minutes=1)
        vehicle_status_resp = VehicleStatusResp(
            statusTime=int(ts_plus_30_s.timestamp()),
            gpsPosition=GpsPosition(
                gpsStatus=GpsStatus.FIX_3d.value,
                timeStamp=int(base_ts.timestamp()),
            ),
        )

        result = get_update_timestamp(vehicle_status_resp)

        assert int(result.timestamp()) != int(ts_plus_30_s.timestamp()), (
            "This test should have NOT selected the vehicle timestamp"
        )

        assert int(result.timestamp()) != int(base_ts.timestamp()), (
            "This test should have NOT selected the GPS timestamp"
        )

        assert result <= datetime.datetime.now(tz=datetime.UTC)

    def test_get_update_should_return_now_if_no_other_info_is_there(self) -> None:
        base_ts = datetime.datetime.now(tz=datetime.UTC) + datetime.timedelta(
            minutes=30
        )
        ts_plus_30_s = base_ts + datetime.timedelta(minutes=1)
        vehicle_status_resp = VehicleStatusResp(
            statusTime=None,
            gpsPosition=GpsPosition(
                gpsStatus=GpsStatus.FIX_3d.value,
                timeStamp=None,
            ),
        )

        result = get_update_timestamp(vehicle_status_resp)

        assert int(result.timestamp()) != int(ts_plus_30_s.timestamp()), (
            "This test should have NOT selected the vehicle timestamp"
        )

        assert int(result.timestamp()) != int(base_ts.timestamp()), (
            "This test should have NOT selected the GPS timestamp"
        )

        assert result <= datetime.datetime.now(tz=datetime.UTC)

    def test_get_update_should_return_now_if_no_other_info_is_there_v2(self) -> None:
        vehicle_status_resp = VehicleStatusResp(
            statusTime=None,
        )

        result = get_update_timestamp(vehicle_status_resp)

        assert result <= datetime.datetime.now(tz=datetime.UTC)

    def test_get_update_should_return_now_if_no_other_info_is_there_v3(self) -> None:
        vehicle_status_resp = VehicleStatusResp(
            gpsPosition=GpsPosition(
                gpsStatus=GpsStatus.FIX_3d.value,
                timeStamp=None,
            )
        )

        result = get_update_timestamp(vehicle_status_resp)

        assert result <= datetime.datetime.now(tz=datetime.UTC)


class TestParseTimezone(TestCase):
    def test_parses_iana_name(self) -> None:
        assert parse_timezone("Australia/Sydney") == ZoneInfo("Australia/Sydney")

    def test_parses_gmt_positive_offset(self) -> None:
        # POSIX Etc/GMT zones use inverted signs: GMT+10:00 → Etc/GMT-10
        assert parse_timezone("GMT+10:00") == ZoneInfo("Etc/GMT-10")

    def test_parses_gmt_negative_offset(self) -> None:
        assert parse_timezone("GMT-05:00") == ZoneInfo("Etc/GMT+5")

    def test_rejects_unknown_format(self) -> None:
        with pytest.raises(ValueError, match="Unrecognized timezone format"):
            parse_timezone("not-a-timezone")


class TestApiTimeoutHelpers:
    @staticmethod
    def _wrapped(cause: BaseException | None) -> SaicApiException:
        exc = SaicApiException("failed", return_code=500)
        exc.__cause__ = cause
        return exc

    def test_is_api_timeout_true_for_httpx_timeout_cause(self) -> None:
        assert is_api_timeout(self._wrapped(httpx.ReadTimeout("t")))

    def test_is_api_timeout_false_for_other_cause(self) -> None:
        assert not is_api_timeout(self._wrapped(httpx.ConnectError("c")))
        assert not is_api_timeout(self._wrapped(None))

    def test_log_api_timeout_traceback_only_in_debug(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        logger = logging.getLogger("test_api_timeout")
        exc = self._wrapped(httpx.ReadTimeout("t"))
        with caplog.at_level(logging.INFO, logger=logger.name):
            log_api_timeout(logger, "ctx", exc)
        assert caplog.records[-1].exc_info is None
        with caplog.at_level(logging.DEBUG, logger=logger.name):
            log_api_timeout(logger, "ctx", exc)
        assert caplog.records[-1].exc_info is not None
