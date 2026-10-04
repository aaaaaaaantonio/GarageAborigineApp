import httpx
import pytest
import respx

from bot.api_client import (
    ApiClient,
    ApiConflict,
    ApiForbidden,
    ApiNotFound,
    ApiUnavailable,
    ApiValidationError,
)


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
async def test_patch_raises_api_forbidden_on_403():
    respx.patch("http://localhost:8000/visits/abc/work-items/xyz/status").mock(
        return_value=httpx.Response(403, json={"detail": "Механик не назначен на эту работу"})
    )
    client = ApiClient()
    with pytest.raises(ApiForbidden, match="Механик не назначен на эту работу"):
        await client.patch("/visits/abc/work-items/xyz/status", json={"new_status": "ready"})


@respx.mock
async def test_search_percent_encodes_user_query():
    route = respx.get("http://localhost:8000/search", params={"q": "Иван & Ко"}).mock(
        return_value=httpx.Response(200, json=[])
    )
    client = ApiClient()
    await client.search("Иван & Ко")
    assert route.called
    assert "q=%D0%98%D0%B2%D0%B0%D0%BD%20%26%20%D0%9A%D0%BE" in str(route.calls.last.request.url)


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


@respx.mock
async def test_get_raises_api_unavailable_on_connection_error():
    respx.get("http://localhost:8000/clients").mock(
        side_effect=httpx.ConnectError("Connection failed")
    )
    client = ApiClient()
    with pytest.raises(ApiUnavailable, match="Сервис временно недоступен"):
        await client.get("/clients")


@respx.mock
async def test_422_with_pydantic_error_list_becomes_readable_text():
    respx.post("http://localhost:8000/clients").mock(
        return_value=httpx.Response(
            422,
            json={
                "detail": [
                    {"loc": ["body", "phone"], "msg": "Field required", "type": "missing"},
                    {"loc": ["body", "full_name"], "msg": "String too short", "type": "string_too_short"},
                ]
            },
        )
    )
    client = ApiClient()
    with pytest.raises(ApiValidationError) as exc_info:
        await client.post("/clients", json={})
    assert isinstance(exc_info.value.message, str)
    assert "phone: Field required" in exc_info.value.message
    assert "full_name: String too short" in exc_info.value.message


@respx.mock
async def test_change_visit_status_sends_reason():
    route = respx.patch("http://localhost:8000/visits/v1/status").mock(
        return_value=httpx.Response(200, json={"id": "v1", "status": "cancelled"})
    )
    await ApiClient().change_visit_status("v1", "cancelled", reason="Клиент передумал")
    import json as _json

    assert _json.loads(route.calls.last.request.content) == {"new_status": "cancelled", "reason": "Клиент передумал"}


@respx.mock
async def test_create_visit_sends_mileage_manually_confirmed():
    route = respx.post("http://localhost:8000/visits").mock(
        return_value=httpx.Response(201, json={"id": "v1", "status": "received"})
    )
    await ApiClient().create_visit(
        client_id="c1", vehicle_id="veh1", assigned_master_id="m1", mileage_at_intake=100,
        mileage_manually_confirmed=True,
    )
    import json as _json

    assert _json.loads(route.calls.last.request.content)["mileage_manually_confirmed"] is True


@respx.mock
async def test_create_visit_409_raises_mileage_rollback():
    from bot.api_client import ApiMileageRollback

    respx.post("http://localhost:8000/visits").mock(
        return_value=httpx.Response(409, json={"detail": "Пробег меньше последнего зафиксированного"})
    )
    with pytest.raises(ApiMileageRollback):
        await ApiClient().create_visit(
            client_id="c1", vehicle_id="veh1", assigned_master_id="m1", mileage_at_intake=100
        )


@respx.mock
async def test_attach_owner_posts_ownership():
    route = respx.post("http://localhost:8000/vehicles/veh1/owners").mock(
        return_value=httpx.Response(201, json={"id": "o1"})
    )
    await ApiClient().attach_owner("veh1", "c1", date_from="2026-09-27")
    import json as _json

    assert _json.loads(route.calls.last.request.content) == {"client_id": "c1", "date_from": "2026-09-27"}


@respx.mock
async def test_get_document_file_returns_bytes():
    respx.get("http://localhost:8000/documents/d1/file").mock(
        return_value=httpx.Response(200, content=b"%PDF-1.7", headers={"content-type": "application/pdf"})
    )
    assert await ApiClient().get_document_file("d1") == b"%PDF-1.7"


@respx.mock
async def test_generate_document_uses_long_timeout():
    route = respx.post("http://localhost:8000/visits/v1/document").mock(
        return_value=httpx.Response(200, json={"document_id": "v1", "document_url": "/x.pdf"})
    )
    await ApiClient().generate_document("v1")
    timeout = route.calls.last.request.extensions["timeout"]
    assert timeout["read"] >= 30


@respx.mock
async def test_list_mechanics_calls_users_mechanics():
    respx.get("http://localhost:8000/users/mechanics").mock(
        return_value=httpx.Response(200, json=[{"id": "m1", "full_name": "Анна"}])
    )
    client = ApiClient()
    assert await client.list_mechanics() == [{"id": "m1", "full_name": "Анна"}]


@respx.mock
async def test_list_visits_passes_filters_as_query():
    route = respx.route(method="GET", host="localhost", path="/visits").mock(
        return_value=httpx.Response(200, json={"items": [], "has_more": False})
    )
    result = await ApiClient(user_id="u1").list_visits(active=True, client_id="c1")
    assert result == {"items": [], "has_more": False}
    assert dict(route.calls.last.request.url.params) == {"active": "true", "client_id": "c1"}


@respx.mock
async def test_navigation_endpoints_hit_expected_paths():
    respx.get("http://localhost:8000/clients/c1/vehicles").mock(return_value=httpx.Response(200, json=[]))
    respx.get("http://localhost:8000/vehicles/v1/owner").mock(return_value=httpx.Response(200, content=b"null"))
    respx.get("http://localhost:8000/users/masters").mock(return_value=httpx.Response(200, json=[]))
    respx.get("http://localhost:8000/vehicles/v1/work-history").mock(
        return_value=httpx.Response(200, json={"items": [], "has_more": False})
    )
    api = ApiClient(user_id="u1")
    assert await api.list_client_vehicles("c1") == []
    assert await api.get_vehicle_owner("v1") is None
    assert await api.list_masters() == []
    assert await api.get_vehicle_work_history("v1") == {"items": [], "has_more": False}
