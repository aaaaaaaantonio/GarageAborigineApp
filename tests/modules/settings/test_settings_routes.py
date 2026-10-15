import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import select

from app.core.enums import UserRole
from app.modules.settings.schemas import PayPatch
from app.modules.users.audit import AuditLog
from app.modules.users.models import User
from tests.helpers import staff_headers
from tests.modules.visits.test_visit_routes import api_app  # noqa: F401


async def _req(api_app, method, path, user, json=None):
    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test") as client:
        return await client.request(method, path, headers=staff_headers(user.id), json=json)


async def _staff(session):
    def user(role, name):
        return User(role=role, full_name=name, branch_id=uuid.uuid4())

    admin, master, mech, admin2 = (user(UserRole.ADMIN, "Иванов"), user(UserRole.MASTER, "Кузнецов"),
                                   user(UserRole.MECHANIC, "Морозов"), user(UserRole.ADMIN, "Орлова"))
    session.add_all([admin, master, mech, admin2])
    await session.flush()
    return admin, master, mech, admin2


OFF = {"mechanic_sees_prices": False, "mechanic_sees_client_name": False,
       "mechanic_sees_client_phone": False, "mechanic_sees_vin": False}


async def test_defaults_are_all_off_and_readable_by_every_role(api_app, session):
    admin, master, mech, _ = await _staff(session)
    for user in (admin, master, mech):
        response = await _req(api_app, "GET", "/settings", user)
        assert response.status_code == 200
        assert response.json() == OFF


async def test_admin_switches_one_setting_and_it_is_audited(api_app, session):
    admin, _, mech, _ = await _staff(session)

    response = await _req(api_app, "PATCH", "/settings", admin, {"mechanic_sees_prices": True})

    assert response.status_code == 200
    assert response.json() == OFF | {"mechanic_sees_prices": True}
    assert (await _req(api_app, "GET", "/settings", mech)).json()["mechanic_sees_prices"] is True
    audit = (await session.execute(select(AuditLog).where(AuditLog.entity_type == "settings"))).scalars().all()
    assert len(audit) == 1 and audit[0].new_value["mechanic_sees_prices"] is True


async def test_only_admin_changes_settings(api_app, session):
    _, master, mech, _ = await _staff(session)
    for user in (master, mech):
        assert (await _req(api_app, "PATCH", "/settings", user, {"mechanic_sees_vin": True})).status_code == 403


async def test_pay_list_is_admin_only_and_lists_active_mechanics(api_app, session):
    admin, master, mech, _ = await _staff(session)

    assert (await _req(api_app, "GET", "/settings/pay", master)).status_code == 403
    response = await _req(api_app, "GET", "/settings/pay", admin)

    assert response.json() == [{"user_id": str(mech.id), "full_name": "Морозов", "pay_scheme": None, "pay_value": None}]


async def test_admin_sets_a_percent_scheme(api_app, session):
    admin, _, mech, _ = await _staff(session)

    response = await _req(api_app, "PATCH", f"/settings/pay/{mech.id}", admin, {"pay_scheme": "percent", "pay_value": 40})

    assert response.status_code == 200
    assert response.json()["pay_scheme"] == "percent" and response.json()["pay_value"] == 40.0
    listed = (await _req(api_app, "GET", "/settings/pay", admin)).json()
    assert (listed[0]["pay_scheme"], listed[0]["pay_value"]) == ("percent", 40.0)
    audit = (await session.execute(select(AuditLog).where(AuditLog.action == "pay_changed"))).scalars().all()
    assert len(audit) == 1 and audit[0].entity_id == mech.id


async def test_pay_value_rules(api_app, session):
    admin, _, mech, admin2 = await _staff(session)
    path = f"/settings/pay/{mech.id}"

    assert (await _req(api_app, "PATCH", path, admin, {"pay_scheme": "percent", "pay_value": 150})).status_code == 422
    assert (await _req(api_app, "PATCH", path, admin, {"pay_scheme": "percent", "pay_value": None})).status_code == 422
    assert (await _req(api_app, "PATCH", path, admin, {"pay_scheme": "per_hour", "pay_value": 0})).status_code == 422
    full = await _req(api_app, "PATCH", path, admin, {"pay_scheme": "full", "pay_value": 5})
    assert (full.status_code, full.json()["pay_value"]) == (200, None)
    assert (await _req(api_app, "PATCH", f"/settings/pay/{admin2.id}", admin,
                       {"pay_scheme": "full", "pay_value": None})).status_code == 422


async def test_masters_do_not_see_pay_in_the_mechanics_list(api_app, session):
    admin, master, mech, _ = await _staff(session)
    await _req(api_app, "PATCH", f"/settings/pay/{mech.id}", admin, {"pay_scheme": "percent", "pay_value": 40})

    listed = (await _req(api_app, "GET", "/users/mechanics", master)).json()

    assert all("pay_scheme" not in u and "pay_value" not in u for u in listed)


async def test_pay_value_must_fit_the_column_and_be_positive_to_the_kopeck(api_app, session):
    admin, _, mech, _ = await _staff(session)
    path = f"/settings/pay/{mech.id}"

    assert (await _req(api_app, "PATCH", path, admin, {"pay_scheme": "per_hour", "pay_value": 1e9})).status_code == 422
    assert (await _req(api_app, "PATCH", path, admin, {"pay_scheme": "per_hour", "pay_value": 1e30})).status_code == 422
    assert (await _req(api_app, "PATCH", path, admin, {"pay_scheme": "per_hour", "pay_value": 0.001})).status_code == 422
    assert (await _req(api_app, "PATCH", path, admin, {"pay_scheme": "percent", "pay_value": 0.001})).status_code == 422


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_pay_value_is_rejected(value):
    with pytest.raises(ValidationError):
        PayPatch(pay_scheme="per_hour", pay_value=value)
