from fastapi import FastAPI

from app.modules.users.router import router as users_router
from app.modules.clients.router import router as clients_router
from app.modules.vehicles.router import router as vehicles_router
from app.modules.catalog.router import router as catalog_router

app = FastAPI(title="CRM Backend")

app.include_router(users_router)
app.include_router(clients_router)
app.include_router(vehicles_router)
app.include_router(catalog_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
