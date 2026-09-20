import httpx
import pytest
import respx

from bot.api_client import ApiClient, ApiConflict, ApiNotFound, ApiUnavailable, ApiValidationError


@respx.mock
async def test_get_returns_json_on_success():
    respx.get("http://localhost:8000/clients/abc").mock(
        return_value=httpx.Response(200, json={"id": "abc"})
    )
    client = ApiClient()
    result = await client.get("/clients/abc")
    assert result == {"id": "abc"}


@respx.mock
async def test_get_raises_api_not_found_on_404():
    respx.get("http://localhost:8000/clients/abc").mock(
        return_value=httpx.Response(404, json={"detail": "Client not found"})
    )
    client = ApiClient()
    with pytest.raises(ApiNotFound, match="Client not found"):
        await client.get("/clients/abc")


@respx.mock
async def test_post_raises_api_conflict_on_409():
    respx.patch("http://localhost:8000/visits/abc/status").mock(
        return_value=httpx.Response(409, json={"detail": "Переход между статусами не разрешён"})
    )
    client = ApiClient()
    with pytest.raises(ApiConflict, match="не разрешён"):
        await client.patch("/visits/abc/status", json={"new_status": "ready"})


@respx.mock
async def test_post_raises_api_validation_error_on_422():
    respx.post("http://localhost:8000/visits").mock(
        return_value=httpx.Response(422, json={"detail": "assigned_master_id должен ссылаться на MASTER"})
    )
    client = ApiClient()
    with pytest.raises(ApiValidationError):
        await client.post("/visits", json={})


@respx.mock
async def test_get_raises_api_unavailable_on_500():
    respx.get("http://localhost:8000/clients").mock(return_value=httpx.Response(500))
    client = ApiClient()
    with pytest.raises(ApiUnavailable):
        await client.get("/clients")


@respx.mock
async def test_requests_carry_x_user_id_header_when_set():
    route = respx.get("http://localhost:8000/clients").mock(return_value=httpx.Response(200, json=[]))
    client = ApiClient(user_id="11111111-1111-1111-1111-111111111111")
    await client.get("/clients")
    assert route.calls.last.request.headers["X-User-Id"] == "11111111-1111-1111-1111-111111111111"


@respx.mock
async def test_get_user_by_telegram_returns_none_on_404():
    respx.get("http://localhost:8000/users/by-telegram/42").mock(
        return_value=httpx.Response(404, json={"detail": "User not found"})
    )
    client = ApiClient()
    assert await client.get_user_by_telegram(42) is None


@respx.mock
async def test_get_user_by_telegram_returns_dict_on_success():
    respx.get("http://localhost:8000/users/by-telegram/42").mock(
        return_value=httpx.Response(200, json={"id": "u1", "role": "master"})
    )
    client = ApiClient()
    result = await client.get_user_by_telegram(42)
    assert result == {"id": "u1", "role": "master"}
