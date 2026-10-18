from __future__ import annotations

import datetime
from importlib.metadata import PackageNotFoundError
import logging
from unittest import TestCase
from unittest.mock import patch
from zoneinfo import ZoneInfo

import httpx
import pytest
from saic_ismart_client_ng.api.schema import GpsPosition, GpsStatus
from saic_ismart_client_ng.api.vehicle import VehicleStatusResp
from saic_ismart_client_ng.exceptions import SaicApiException, SaicApiRetryException

from utils import (
    get_gateway_version,
    get_update_timestamp,
    is_transient_api_error,
    log_transient_api_error,
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

    def test_is_transient_api_error_true_for_httpx_timeout_cause(self) -> None:
        assert is_transient_api_error(self._wrapped(httpx.ReadTimeout("t")))

    def test_is_transient_api_error_true_for_retry_exception(self) -> None:
        exc = SaicApiRetryException("try again later", event_id="1", return_code=4)
        assert is_transient_api_error(exc)

    def test_is_transient_api_error_false_for_other_cause(self) -> None:
        assert not is_transient_api_error(self._wrapped(httpx.ConnectError("c")))
        assert not is_transient_api_error(self._wrapped(None))

    def test_log_transient_api_error_traceback_only_in_debug(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        logger = logging.getLogger("test_api_timeout")
        exc = self._wrapped(httpx.ReadTimeout("t"))
        with caplog.at_level(logging.INFO, logger=logger.name):
            log_transient_api_error(logger, "ctx", exc)
        assert caplog.records[-1].exc_info is None
        with caplog.at_level(logging.DEBUG, logger=logger.name):
            log_transient_api_error(logger, "ctx", exc)
        assert caplog.records[-1].exc_info is not None

    def test_log_transient_api_error_level(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        logger = logging.getLogger("test_api_level")
        exc = self._wrapped(httpx.ReadTimeout("t"))
        with caplog.at_level(logging.INFO, logger=logger.name):
            log_transient_api_error(logger, "ctx", exc)
            assert caplog.records[-1].levelno == logging.WARNING
            log_transient_api_error(logger, "ctx", exc, level=logging.ERROR)
            assert caplog.records[-1].levelno == logging.ERROR


class TestGetGatewayVersion:
    def test_release_version_env_wins_over_package_metadata(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RELEASE_VERSION", "1.2.3")
        with patch("utils.version", return_value="0.11.0"):
            assert get_gateway_version() == "1.2.3"

    def test_falls_back_to_package_metadata(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("RELEASE_VERSION", raising=False)
        with patch("utils.version", return_value="0.11.0"):
            assert get_gateway_version() == "0.11.0"

    def test_empty_release_version_is_ignored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RELEASE_VERSION", "")
        with patch("utils.version", return_value="0.11.0"):
            assert get_gateway_version() == "0.11.0"

    def test_unknown_without_env_or_metadata(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("RELEASE_VERSION", raising=False)
        with patch("utils.version", side_effect=PackageNotFoundError):
            assert get_gateway_version() == "unknown"
