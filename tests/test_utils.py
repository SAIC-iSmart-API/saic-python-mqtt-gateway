from __future__ import annotations

import datetime
from unittest import TestCase

from saic_ismart_client_ng.api.schema import GpsPosition, GpsStatus
from saic_ismart_client_ng.api.vehicle import VehicleStatusResp

from utils import get_update_timestamp


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

        assert int(result.timestamp()) is not None, (
            "This test should have returned a timestamp"
        )

        assert result <= datetime.datetime.now(tz=datetime.UTC)

    def test_get_update_should_return_now_if_no_other_info_is_there_v3(self) -> None:
        vehicle_status_resp = VehicleStatusResp(
            gpsPosition=GpsPosition(
                gpsStatus=GpsStatus.FIX_3d.value,
                timeStamp=None,
            )
        )

        result = get_update_timestamp(vehicle_status_resp)

        assert int(result.timestamp()) is not None, (
            "This test should have returned a timestamp"
        )

        assert result <= datetime.datetime.now(tz=datetime.UTC)
