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


class ApiValidationError(ApiError):
    pass


class ApiUnavailable(ApiError):
    pass


class ApiClient:
    def __init__(self, user_id: str | None = None):
        self.user_id = user_id

    def _headers(self) -> dict[str, str]:
        if self.user_id is None:
            return {}
        return {"X-User-Id": str(self.user_id)}

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        try:
            detail = response.json().get("detail", "")
        except Exception:
            detail = ""
        if response.status_code == 404:
            raise ApiNotFound(detail or "Не найдено")
        if response.status_code == 409:
            raise ApiConflict(detail or "Конфликт")
        if response.status_code == 422:
            raise ApiValidationError(detail or "Некорректные данные")
        raise ApiUnavailable("Сервис временно недоступен, попробуйте позже")

    async def get(self, path: str) -> dict | list:
        try:
            async with httpx.AsyncClient(base_url=settings.api_base_url) as client:
                response = await client.get(path, headers=self._headers())
        except httpx.HTTPError:
            raise ApiUnavailable("Сервис временно недоступен, попробуйте позже")
        self._raise_for_status(response)
        return response.json()

    async def post(self, path: str, json: dict | None = None) -> dict | list:
        try:
            async with httpx.AsyncClient(base_url=settings.api_base_url) as client:
                response = await client.post(path, json=json or {}, headers=self._headers())
        except httpx.HTTPError:
            raise ApiUnavailable("Сервис временно недоступен, попробуйте позже")
        self._raise_for_status(response)
        return response.json()

    async def patch(self, path: str, json: dict | None = None) -> dict | list:
        try:
            async with httpx.AsyncClient(base_url=settings.api_base_url) as client:
                response = await client.patch(path, json=json or {}, headers=self._headers())
        except httpx.HTTPError:
            raise ApiUnavailable("Сервис временно недоступен, попробуйте позже")
        self._raise_for_status(response)
        return response.json()

    async def get_user_by_telegram(self, telegram_id: int) -> dict | None:
        try:
            return await self.get(f"/users/by-telegram/{telegram_id}")
        except ApiNotFound:
            return None

    async def search(self, query: str) -> list[dict]:
        result = await self.get(f"/search?q={query}")
        return result

    async def create_client(self, full_name: str, phone: str) -> dict:
        return await self.post("/clients", json={"full_name": full_name, "phone": phone})
