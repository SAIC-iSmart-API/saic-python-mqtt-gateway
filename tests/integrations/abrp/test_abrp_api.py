from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest
import pytest_asyncio

from integrations.abrp.api import AbrpApi, AbrpApiException

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from saic_ismart_client_ng.api.vehicle import VehicleStatusResp
    from saic_ismart_client_ng.api.vehicle_charging import ChrgMgmtDataResp
from tests.common_mocks import (
    get_mock_charge_management_data_resp,
    get_mock_vehicle_status_resp,
)


@pytest.fixture
def vehicle_status() -> VehicleStatusResp:
    return get_mock_vehicle_status_resp()


@pytest.fixture
def charge_info() -> ChrgMgmtDataResp:
    return get_mock_charge_management_data_resp()


@pytest_asyncio.fixture
async def abrp_api() -> AsyncIterator[AbrpApi]:
    api = AbrpApi(
        abrp_api_key="test_api_key",
        abrp_user_token="test_user_token",  # noqa: S106
    )
    yield api
    await api.close()


async def _set_mock_transport(api: AbrpApi, status_code: int, text: str) -> None:
    await api.client.aclose()
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(status_code, text=text)
    )
    api.client = httpx.AsyncClient(transport=transport)


@pytest.mark.asyncio
async def test_raise_for_status_on_server_error(
    abrp_api: AbrpApi,
    vehicle_status: VehicleStatusResp,
    charge_info: ChrgMgmtDataResp,
) -> None:
    await _set_mock_transport(abrp_api, 500, "Internal Server Error")

    with pytest.raises(AbrpApiException, match="500"):
        await abrp_api.update_abrp(
            vehicle_status=vehicle_status,
            charge_info=charge_info,
        )


@pytest.mark.asyncio
async def test_raise_for_status_on_client_error(
    abrp_api: AbrpApi,
    vehicle_status: VehicleStatusResp,
    charge_info: ChrgMgmtDataResp,
) -> None:
    await _set_mock_transport(abrp_api, 403, "Forbidden")

    with pytest.raises(AbrpApiException, match="403"):
        await abrp_api.update_abrp(
            vehicle_status=vehicle_status,
            charge_info=charge_info,
        )


@pytest.mark.asyncio
async def test_success_on_200(
    abrp_api: AbrpApi,
    vehicle_status: VehicleStatusResp,
    charge_info: ChrgMgmtDataResp,
) -> None:
    await _set_mock_transport(abrp_api, 200, '{"status": "ok"}')

    success, response = await abrp_api.update_abrp(
        vehicle_status=vehicle_status,
        charge_info=charge_info,
    )
    assert success
    assert response == '{"status": "ok"}'


@pytest.mark.asyncio
async def test_skips_when_missing_config(
    vehicle_status: VehicleStatusResp,
    charge_info: ChrgMgmtDataResp,
) -> None:
    api = AbrpApi(abrp_api_key=None, abrp_user_token=None)
    success, _response = await api.update_abrp(
        vehicle_status=vehicle_status,
        charge_info=charge_info,
    )
    assert not success
    await api.close()


@pytest.mark.asyncio
async def test_skip_reason_lists_missing_config(
    vehicle_status: VehicleStatusResp,
    charge_info: ChrgMgmtDataResp,
) -> None:
    api = AbrpApi(abrp_api_key=None, abrp_user_token=None)
    _success, response = await api.update_abrp(
        vehicle_status=vehicle_status,
        charge_info=charge_info,
    )
    assert "ABRP API key" in response
    assert "ABRP user token" in response
    await api.close()


@pytest.mark.asyncio
async def test_skip_reason_reports_missing_charge_data(
    abrp_api: AbrpApi,
    vehicle_status: VehicleStatusResp,
) -> None:
    success, response = await abrp_api.update_abrp(
        vehicle_status=vehicle_status,
        charge_info=None,
    )
    assert not success
    assert "charge management data" in response
    assert "token" not in response
