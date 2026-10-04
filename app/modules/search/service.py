import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.clients.models import Client
from app.modules.search.config import SEARCH_FIELDS, MatchType
from app.modules.search.models import RecentView
from app.modules.vehicles.models import Vehicle

ENTITY_MODELS = {"client": Client, "vehicle": Vehicle}


class SearchService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def search(self, query: str, entities: set[str] | None = None) -> list[dict]:
        results: list[dict] = []
        seen: set[tuple[str, uuid.UUID]] = set()

        for field in SEARCH_FIELDS:
            if entities is not None and field.entity not in entities:
                continue
            model = ENTITY_MODELS[field.entity]
            column = getattr(model, field.field)

            if field.match_type == MatchType.EXACT:
                stmt = select(model).where(column == query, model.deleted_at.is_(None))
            elif field.match_type == MatchType.NORMALIZED:
                assert field.normalizer is not None
                stmt = select(model).where(column == field.normalizer(query), model.deleted_at.is_(None))
            elif field.match_type == MatchType.EXACT_OR_SUFFIX:
                if len(query) <= 4:
                    stmt = select(model).where(column.like(f"%{query.upper()}"), model.deleted_at.is_(None))
                else:
                    stmt = select(model).where(column == query.upper(), model.deleted_at.is_(None))
            elif field.match_type == MatchType.FUZZY:
                # word_similarity compares the query with the best-matching part
                # of the column, so "Никитин" finds "Никитин Антон Александрович";
                # plain similarity() scores it against the whole string and misses.
                stmt = (
                    select(model)
                    .where(
                        model.deleted_at.is_(None),
                        text(f"word_similarity(:q, {field.field}) >= :threshold"),
                    )
                    .order_by(
                        text(f"word_similarity(:q, {field.field}) DESC"),
                        text(f"similarity({field.field}, :q) DESC"),
                    )
                    .params(q=query, threshold=settings.search_fuzzy_threshold)
                )
            else:
                continue

            rows = (await self.session.execute(stmt)).scalars()
            for row in rows:
                key = (field.entity, row.id)
                if key in seen:
                    continue
                seen.add(key)
                results.append({"entity": field.entity, "id": row.id, "matched_field": field.field})

        return results

    async def record_view(self, user_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID) -> None:
        self.session.add(RecentView(user_id=user_id, entity_type=entity_type, entity_id=entity_id))
        await self.session.flush()

    async def recent(self, user_id: uuid.UUID) -> list[RecentView]:
        stmt = (
            select(RecentView)
            .where(RecentView.user_id == user_id)
            .order_by(RecentView.viewed_at.desc())
            .limit(settings.recent_views_limit)
        )
        return list((await self.session.execute(stmt)).scalars())
