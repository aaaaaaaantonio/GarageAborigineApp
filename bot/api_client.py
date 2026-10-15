from urllib.parse import quote, urlencode

import httpx

from bot.config import settings


class ApiError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ApiNotFound(ApiError):
    pass


class ApiConflict(ApiError):
    pass


class ApiForbidden(ApiError):
    pass


class ApiValidationError(ApiError):
    pass


class ApiUnavailable(ApiError):
    pass


class ApiMileageRollback(ApiConflict):
    """Пробег меньше последнего зафиксированного — нужен явный повтор с подтверждением."""


_UNAVAILABLE_TEXT = "Сервис временно недоступен, попробуйте позже"
_DEFAULT_TIMEOUT = 5.0
_PDF_TIMEOUT = 30.0


def _detail_text(detail) -> str:
    """FastAPI отдаёт detail строкой (HTTPException) или списком ошибок pydantic (422)."""
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        parts = []
        for error in detail:
            if not isinstance(error, dict):
                parts.append(str(error))
                continue
            loc = [str(p) for p in error.get("loc", []) if p != "body"]
            msg = error.get("msg", "")
            parts.append(f"{'.'.join(loc)}: {msg}" if loc else msg)
        return "; ".join(p for p in parts if p)
    return ""


def _query(params: dict) -> str:
    """`?a=1&s=x&s=y`: lists repeat the key; None, False and empty lists are left out."""
    pairs = []
    for key, value in params.items():
        if value is None or value is False or value == []:
            continue
        if isinstance(value, list):
            pairs.extend((key, v) for v in value)
        else:
            pairs.append((key, "true" if value is True else str(value)))
    return f"?{urlencode(pairs)}" if pairs else ""


class ApiClient:
    def __init__(self, user_id: str | None = None):
        self.user_id = user_id

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if settings.internal_api_key:
            headers["X-Service-Key"] = settings.internal_api_key
        if self.user_id is not None:
            headers["X-User-Id"] = str(self.user_id)
        return headers

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        try:
            detail = _detail_text(response.json().get("detail", ""))
        except Exception:
            detail = ""
        if response.status_code == 404:
            raise ApiNotFound(detail or "Не найдено")
        if response.status_code == 409:
            raise ApiConflict(detail or "Конфликт")
        if response.status_code == 422:
            raise ApiValidationError(detail or "Некорректные данные")
        if response.status_code == 403:
            raise ApiForbidden(detail or "Недостаточно прав")
        raise ApiUnavailable(_UNAVAILABLE_TEXT)

    async def _request(
        self, method: str, path: str, json: dict | None = None, timeout: float = _DEFAULT_TIMEOUT
    ) -> httpx.Response:
        kwargs = {"headers": self._headers()}
        if method != "GET":
            kwargs["json"] = json or {}
        try:
            async with httpx.AsyncClient(base_url=settings.api_base_url, timeout=timeout) as client:
                response = await client.request(method, path, **kwargs)
        except httpx.HTTPError:
            raise ApiUnavailable(_UNAVAILABLE_TEXT)
        self._raise_for_status(response)
        return response

    async def get(self, path: str) -> dict | list:
        return (await self._request("GET", path)).json()

    async def post(self, path: str, json: dict | None = None, timeout: float = _DEFAULT_TIMEOUT) -> dict | list:
        return (await self._request("POST", path, json=json, timeout=timeout)).json()

    async def patch(self, path: str, json: dict | None = None) -> dict | list:
        return (await self._request("PATCH", path, json=json)).json()

    async def get_user_by_telegram(self, telegram_id: int) -> dict | None:
        try:
            return await self.get(f"/users/by-telegram/{telegram_id}")
        except ApiNotFound:
            return None

    async def get_client(self, client_id: str) -> dict:
        return await self.get(f"/clients/{client_id}")

    async def get_vehicle(self, vehicle_id: str) -> dict:
        return await self.get(f"/vehicles/{vehicle_id}")

    async def suggest_catalog(self, text: str) -> list[dict]:
        return await self.get(f"/catalog/suggest?text={quote(text, safe='')}")

    async def add_work_item(self, visit_id: str, **fields) -> dict:
        return await self.post(f"/visits/{visit_id}/work-items", json=fields)

    async def list_mechanics(self) -> list[dict]:
        return await self.get("/users/mechanics")

    async def list_my_work_items(self, status: list[str] | None = None, sort: str | None = None) -> list[dict]:
        return await self.get(f"/work-items/mine{_query({'status': status, 'sort': sort})}")

    async def list_my_done_work_items(self, since: str | None = None, outcome: str | None = None) -> dict:
        return await self.get(f"/work-items/mine/done{_query({'since': since, 'outcome': outcome})}")

    async def get_mechanic_view(self, visit_id: str) -> dict:
        return await self.get(f"/visits/{visit_id}/mechanic-view")

    async def get_stats(self, section: str, period: str, master_id: str | None = None) -> dict:
        return await self.get(f"/stats/{section}{_query({'period': period, 'master_id': master_id})}")

    async def get_my_stats(self, period: str) -> dict:
        return await self.get(f"/stats/mine{_query({'period': period})}")

    async def get_settings(self) -> dict:
        return await self.get("/settings")

    async def update_settings(self, **changes) -> dict:
        return await self.patch("/settings", json=changes)

    async def list_mechanic_pay(self) -> list[dict]:
        return await self.get("/settings/pay")

    async def set_mechanic_pay(self, user_id: str, scheme: str | None, value: float | None) -> dict:
        return await self.patch(f"/settings/pay/{user_id}", json={"pay_scheme": scheme, "pay_value": value})

    async def list_work_board(self, **filters) -> dict:
        """Filters as in GET /work-items/board: mechanic_id, unassigned, status, category, unapproved, group."""
        return await self.get(f"/work-items/board{_query(filters)}")

    async def update_work_item_status(self, visit_id: str, item_id: str, new_status: str) -> dict:
        return await self.patch(f"/visits/{visit_id}/work-items/{item_id}/status", json={"new_status": new_status})

    async def assign_work_item_mechanic(self, visit_id: str, item_id: str, mechanic_id: str | None) -> dict:
        return await self.patch(
            f"/visits/{visit_id}/work-items/{item_id}/mechanic", json={"assigned_mechanic_id": mechanic_id}
        )

    async def search(self, query: str) -> list[dict]:
        result = await self.get(f"/search?q={quote(query, safe='')}")
        return result

    async def create_client(self, full_name: str, phone: str) -> dict:
        return await self.post("/clients", json={"full_name": full_name, "phone": phone})

    async def create_vehicle(self, vin: str, plate_number: str, make: str, model: str) -> dict:
        return await self.post(
            "/vehicles", json={"vin": vin, "plate_number": plate_number, "make": make, "model": model}
        )

    async def attach_owner(self, vehicle_id: str, client_id: str, date_from: str) -> dict:
        return await self.post(f"/vehicles/{vehicle_id}/owners", json={"client_id": client_id, "date_from": date_from})

    async def create_visit(
        self,
        client_id: str,
        vehicle_id: str,
        assigned_master_id: str,
        mileage_at_intake: int,
        mileage_manually_confirmed: bool = False,
    ) -> dict:
        try:
            return await self.post(
                "/visits",
                json={
                    "client_id": client_id,
                    "vehicle_id": vehicle_id,
                    "assigned_master_id": assigned_master_id,
                    "mileage_at_intake": mileage_at_intake,
                    "mileage_manually_confirmed": mileage_manually_confirmed,
                },
            )
        except ApiConflict:
            # POST /visits returns 409 only for MileageRollbackNotConfirmed.
            raise ApiMileageRollback("Пробег меньше последнего зафиксированного. Подтвердите пробег, если он верный.")

    async def change_visit_status(self, visit_id: str, new_status: str, reason: str | None = None) -> dict:
        payload = {"new_status": new_status}
        if reason is not None:
            payload["reason"] = reason
        return await self.patch(f"/visits/{visit_id}/status", json=payload)

    async def get_visit(self, visit_id: str) -> dict:
        return await self.get(f"/visits/{visit_id}")

    async def list_work_items(self, visit_id: str) -> list[dict]:
        return await self.get(f"/visits/{visit_id}/work-items")

    async def approve_work_item(self, visit_id: str, item_id: str) -> dict:
        return await self.post(f"/visits/{visit_id}/work-items/{item_id}/approve")

    async def add_part_item(
        self, visit_id: str, work_item_id: str, name: str, quantity: int, unit_price: float
    ) -> dict:
        return await self.post(
            f"/visits/{visit_id}/part-items",
            json={"work_item_id": work_item_id, "name": name, "quantity": quantity, "unit_price": unit_price},
        )

    async def generate_document(self, visit_id: str) -> dict:
        return await self.post(f"/visits/{visit_id}/document", timeout=_PDF_TIMEOUT)

    async def get_document_file(self, document_id: str) -> bytes:
        return (await self._request("GET", f"/documents/{document_id}/file", timeout=_PDF_TIMEOUT)).content

    async def register_paper_consent(self, full_name: str, phone: str) -> dict:
        return await self.post("/consent/paper", json={"full_name": full_name, "phone": phone})

    async def create_staff_user(self, role: str, full_name: str, telegram_id: int | None) -> dict:
        return await self.post(
            "/users", json={"role": role, "full_name": full_name, "telegram_id": telegram_id}
        )

    async def list_visits(self, **filters) -> dict:
        """Filters as in GET /visits: active, closed, status (list), client_id, vehicle_id,
        master_id, unassigned_work, stale, since, sort, offset."""
        return await self.get(f"/visits{_query(filters)}")

    async def list_client_vehicles(self, client_id: str) -> list[dict]:
        return await self.get(f"/clients/{client_id}/vehicles")

    async def get_vehicle_owner(self, vehicle_id: str) -> dict | None:
        return await self.get(f"/vehicles/{vehicle_id}/owner")

    async def list_masters(self) -> list[dict]:
        return await self.get("/users/masters")

    async def get_vehicle_work_history(self, vehicle_id: str, category: list[str] | None = None) -> dict:
        return await self.get(f"/vehicles/{vehicle_id}/work-history{_query({'category': category})}")
