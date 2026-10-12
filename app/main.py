import logging

from fastapi import FastAPI

from app.core.config import settings
from app.core.logging import install_access_log_filter

from app.modules.auth.router import router as auth_router
from app.modules.users.router import router as users_router
from app.modules.clients.router import router as clients_router
from app.modules.vehicles.router import router as vehicles_router
from app.modules.catalog.router import router as catalog_router
from app.modules.visits.router import router as visits_router
from app.modules.visits.work_items_router import router as work_items_router
from app.modules.visits.work_items_mine_router import router as work_items_mine_router
from app.modules.visits.part_items_router import router as part_items_router
from app.modules.visits.vehicle_history_router import router as vehicle_history_router
from app.modules.consent.router import router as consent_router
from app.modules.search.router import router as search_router
from app.modules.documents.router import files_router as document_files_router
from app.modules.documents.router import router as documents_router

install_access_log_filter()

if not settings.internal_api_key:
    logging.getLogger(__name__).warning("INTERNAL_API_KEY не задан: запросы бота с X-User-Id будут отклоняться (401)")

app = FastAPI(title="CRM Backend")

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(clients_router)
app.include_router(vehicles_router)
app.include_router(catalog_router)
app.include_router(visits_router)
app.include_router(work_items_router)
app.include_router(work_items_mine_router)
app.include_router(part_items_router)
app.include_router(vehicle_history_router)
app.include_router(consent_router)
app.include_router(search_router)
app.include_router(documents_router)
app.include_router(document_files_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
