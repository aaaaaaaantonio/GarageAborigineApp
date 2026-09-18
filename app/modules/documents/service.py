import uuid

import weasyprint
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.clients.models import Client
from app.modules.documents.storage import FileStorage, LocalFileStorage
from app.modules.vehicles.models import Vehicle
from app.modules.visits.models import Visit, VisitPartItem, VisitWorkItem

TEMPLATE_DIR = __file__.rsplit("/", 1)[0] + "/templates"
jinja_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))


class DocumentService:
    def __init__(self, session: AsyncSession, storage: FileStorage | None = None):
        self.session = session
        self.storage = storage or LocalFileStorage()

    async def generate_visit_document(self, visit_id: uuid.UUID) -> str:
        visit = await self.session.get(Visit, visit_id)
        assert visit is not None
        client = await self.session.get(Client, visit.client_id)
        vehicle = await self.session.get(Vehicle, visit.vehicle_id)

        work_items = list(
            (await self.session.execute(select(VisitWorkItem).where(VisitWorkItem.visit_id == visit_id))).scalars()
        )
        part_items = list(
            (await self.session.execute(select(VisitPartItem).where(VisitPartItem.visit_id == visit_id))).scalars()
        )

        template = jinja_env.get_template("visit_order.html")
        html = template.render(
            visit=visit,
            client=client,
            vehicle=vehicle,
            work_items=[{"free_text_name": w.free_text_name, "catalog_item_name": None, **w.__dict__} for w in work_items],
            part_items=part_items,
        )

        pdf_bytes = weasyprint.HTML(string=html).write_pdf()
        url = self.storage.save(pdf_bytes, f"visits/{visit_id}.pdf")

        visit.document_url = url
        await self.session.flush()
        return url
