from app.core.enums import PayScheme, VisitStatus
from app.modules.settings.schemas import VisibilityPatch
from app.modules.settings.service import SettingsService
from tests.modules.stats.helpers import msk, part, visit, work, world
from tests.modules.visits.test_visit_routes import _get, api_app  # noqa: F401

PRICE_FIELDS = ("discount", "total_amount", "my_pay_total")
CLIENT_FIELDS = ("client_name", "client_phone", "client_telegram_username", "vin")


async def _setup(session, status=VisitStatus.IN_PROGRESS):
    w = await world(session)
    v = await visit(session, w, master=w.master_a, created=msk(10, 9), status=status, total=3200)
    w.own = await work(session, v, name="Масло", hours=2, rate=1000, mechanic=w.mech_a)
    await part(session, v, w.own, qty=2, price=300)
    await work(session, v, name="Рычаг", hours=1, rate=1000, mechanic=w.mech_b)
    await work(session, v, name="Ничья", hours=0.5, rate=1000)
    w.v = v
    return w


async def _view(api_app, w, user=None):
    return await _get(api_app, f"/visits/{w.v.id}/mechanic-view", user or w.mech_a)


async def test_only_a_mechanic_with_a_work_in_the_visit_may_open_it(api_app, session):
    w = await _setup(session)
    stranger = await visit(session, w, master=w.master_a, created=msk(10, 9), status=VisitStatus.IN_PROGRESS)
    await work(session, stranger, name="Чужое", hours=1, rate=1000, mechanic=w.mech_b)

    assert (await _view(api_app, w)).status_code == 200
    assert (await _get(api_app, f"/visits/{stranger.id}/mechanic-view", w.mech_a)).status_code == 403
    assert (await _view(api_app, w, w.master_a)).status_code == 403
    assert (await _get(api_app, "/visits/00000000-0000-0000-0000-000000000000/mechanic-view", w.mech_a)).status_code == 404


async def test_closed_visits_open_too(api_app, session):
    w = await _setup(session, VisitStatus.ISSUED)
    assert (await _view(api_app, w)).status_code == 200
    # One world per session: a second visit reuses it (world() creates a fixed client phone and VIN).
    w.v = await visit(session, w, master=w.master_a, created=msk(10, 9), status=VisitStatus.CANCELLED)
    await work(session, w.v, name="Масло", hours=2, rate=1000, mechanic=w.mech_a)
    assert (await _view(api_app, w)).status_code == 200


async def test_by_default_no_prices_and_no_client_data(api_app, session):
    w = await _setup(session)

    body = (await _view(api_app, w)).json()

    assert (body["plate_number"], body["make_model"], body["master_name"]) == ("А123ВС77", "Toyota Camry", "Кузнецов")
    assert all(body[k] is None for k in PRICE_FIELDS + CLIENT_FIELDS)
    works = {x["name"]: x for x in body["works"]}
    assert set(works) == {"Масло", "Рычаг", "Ничья"}
    assert (works["Масло"]["is_mine"], works["Рычаг"]["mechanic_name"], works["Ничья"]["mechanic_name"]) == (True, "Соколов", None)
    assert works["Масло"]["norm_hours"] == 2
    assert all(x[k] is None for x in body["works"] for k in ("hourly_rate", "amount", "my_pay"))
    assert works["Масло"]["parts"][0] | {} == {"name": "Запчасть", "article_number": None, "quantity": 2,
                                               "availability_status": "in_stock", "unit_price": None, "amount": None}


async def test_everything_switched_on(api_app, session):
    w = await _setup(session)
    w.mech_a.pay_scheme, w.mech_a.pay_value = PayScheme.PERCENT, 50
    await SettingsService(session).update_visibility(VisibilityPatch(
        mechanic_sees_prices=True, mechanic_sees_client_name=True, mechanic_sees_client_phone=True, mechanic_sees_vin=True,
    ), w.admin)

    body = (await _view(api_app, w)).json()

    assert body["client_name"] == "Петров Иван" and "999" in body["client_phone"] and body["vin"] == "A" * 17
    assert (body["total_amount"], body["discount"], body["my_pay_total"]) == (3200, 0, 1000)
    works = {x["name"]: x for x in body["works"]}
    assert (works["Масло"]["hourly_rate"], works["Масло"]["amount"], works["Масло"]["my_pay"]) == (1000, 2000, 1000)
    assert (works["Рычаг"]["amount"], works["Рычаг"]["my_pay"]) == (1000, None)
    assert (works["Масло"]["parts"][0]["unit_price"], works["Масло"]["parts"][0]["amount"]) == (300, 600)


async def test_each_switch_opens_only_its_fields(api_app, session):
    w = await _setup(session)
    await SettingsService(session).update_visibility(VisibilityPatch(mechanic_sees_client_phone=True), w.admin)

    body = (await _view(api_app, w)).json()

    assert body["client_phone"] is not None
    assert (body["client_name"], body["vin"], body["total_amount"]) == (None, None, None)


async def test_prices_on_without_a_scheme_shows_no_pay(api_app, session):
    w = await _setup(session)
    await SettingsService(session).update_visibility(VisibilityPatch(mechanic_sees_prices=True), w.admin)

    body = (await _view(api_app, w)).json()

    assert body["total_amount"] == 3200
    assert body["my_pay_total"] is None
    assert {x["name"]: x["my_pay"] for x in body["works"]}["Масло"] is None


async def test_snapshot_is_shown_for_issued_visits(api_app, session):
    w = await _setup(session, VisitStatus.ISSUED)
    w.mech_a.pay_scheme, w.mech_a.pay_value = PayScheme.FULL, None
    w.own.mechanic_pay = 777
    await session.flush()
    await SettingsService(session).update_visibility(VisibilityPatch(mechanic_sees_prices=True), w.admin)

    body = (await _view(api_app, w)).json()

    assert body["my_pay_total"] == 777
