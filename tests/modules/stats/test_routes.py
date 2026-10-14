# tests/modules/stats/test_routes.py
from tests.modules.stats.helpers import world
from tests.modules.visits.test_visit_routes import _get, api_app  # noqa: F401


async def test_admin_gets_a_section(api_app, session):
    w = await world(session)

    resp = await _get(api_app, "/stats/money?period=week", w.admin)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["section"] == "money" and body["period"] == "week"
    assert [k["key"] for k in body["kpis"]] == ["revenue", "avg_check", "issued", "work_share"]


async def test_sections_are_admin_only(api_app, session):
    w = await world(session)

    assert (await _get(api_app, "/stats/money", w.master_a)).status_code == 403
    assert (await _get(api_app, "/stats/money", w.mech_a)).status_code == 403


async def test_unknown_section_or_period_is_422(api_app, session):
    w = await world(session)

    assert (await _get(api_app, "/stats/salaries", w.admin)).status_code == 422
    assert (await _get(api_app, "/stats/money?period=decade", w.admin)).status_code == 422
