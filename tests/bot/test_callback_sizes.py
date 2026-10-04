"""Every button of every screen fits Telegram's 64-byte callback_data limit."""
from unittest.mock import AsyncMock

from bot import nav
from tests.bot.helpers import ADMIN, MECHANIC, buttons

# UUIDs encode to 22 chars regardless of value; use distinct ones.
V, I, M, C, CAR = (f"{n}" * 8 + "-" + f"{n}" * 4 + "-" + f"{n}" * 4 + "-" + f"{n}" * 4 + "-" + f"{n}" * 12 for n in range(1, 6))


def _api():
    api = AsyncMock()
    item = {"id": I, "visit_id": V, "name": "Очень длинное название работы", "status": "waiting_parts",
            "approved_by_client": False, "assigned_mechanic_name": "Механик", "plate_number": "А123ВС77", "make_model": "X Y"}
    api.get_visit.return_value = {"id": V, "status": "in_progress", "total_amount": 1, "plate_number": "А1"}
    api.list_work_items.return_value = [item]
    api.list_my_work_items.return_value = [item]
    api.list_mechanics.return_value = [{"id": M, "full_name": "Механик"}]
    api.list_visits.return_value = {"items": [{"id": V, "status": "in_progress", "plate_number": "А1", "client_name": "К",
                                               "assigned_master_id": M, "created_at": "2026-10-02T07:00:00+00:00"}], "has_more": False}
    api.get_client.return_value = {"id": C, "full_name": "К", "phone_display": "+7"}
    api.list_client_vehicles.return_value = [{"id": CAR, "make": "A", "model": "B", "plate_number": "А1"}]
    api.get_vehicle.return_value = {"id": CAR, "make": "A", "model": "B", "plate_number": "А1", "vin": "X" * 17, "mileage_current": 1}
    api.get_vehicle_owner.return_value = {"id": C, "full_name": "К"}
    api.search.return_value = [{"entity": "vehicle", "id": CAR}] * 25
    return api


SCREEN_ARGS = {
    "menu": {}, "active_visits": {}, "my_works": {}, "search": {},
    "visit": {"visit_id": V}, "visit_status": {"visit_id": V},
    "work": {"visit_id": V, "item_id": I}, "reassign": {"visit_id": V, "item_id": I},
    "client": {"client_id": C}, "vehicle": {"vehicle_id": CAR},
    "client_visits": {"client_id": C}, "vehicle_visits": {"vehicle_id": CAR}, "work_history": {"vehicle_id": CAR},
    "search_results": {"query": "A", "page": 1},
}


def test_every_screen_is_covered():
    assert set(SCREEN_ARGS) == set(nav.SCREENS) - {name for name in nav.SCREENS if name.startswith(("t_", "w_"))}


async def test_all_screen_buttons_fit_64_bytes():
    for user in (ADMIN, MECHANIC):
        for name, args in SCREEN_ARGS.items():
            _, markup = await nav.SCREENS[name].render(_api(), user, args)
            for text, data in buttons(markup):
                assert len(data.encode()) <= 64, (name, text, data)
