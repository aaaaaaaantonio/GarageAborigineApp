import uuid
from datetime import datetime, timezone

import pytest

from app.core.enums import VisitStatus, WorkItemStatus
from app.modules.visits.fsm import ALLOWED_TRANSITIONS
from app.modules.visits.schemas import VisitOut
from app.modules.visits.work_item_flow import WORK_ITEM_NEXT_STATUSES
from app.modules.visits.work_items_schemas import WorkItemMineOut, WorkItemOut


def _visit(status: VisitStatus) -> VisitOut:
    return VisitOut(
        id=uuid.uuid4(), status=status, mileage_at_intake=1, total_amount=0, created_at=datetime.now(timezone.utc),
        client_id=uuid.uuid4(), client_name="К", vehicle_id=uuid.uuid4(), plate_number="А123ВС77",
        make_model="Kia Rio", assigned_master_id=uuid.uuid4(), master_name="М",
    )


@pytest.mark.parametrize("status", list(VisitStatus))
def test_visit_allowed_next_matches_fsm(status):
    out = _visit(status).model_dump(mode="json")
    expected = [s.value for s in VisitStatus if s in ALLOWED_TRANSITIONS[status]]
    assert out["allowed_next_statuses"] == expected


def test_in_progress_visit_order():
    assert _visit(VisitStatus.IN_PROGRESS).model_dump(mode="json")["allowed_next_statuses"] == [
        "waiting_parts", "ready", "cancelled",
    ]


def test_work_item_flow_matches_bot_hint():
    assert WORK_ITEM_NEXT_STATUSES == {
        WorkItemStatus.NOT_READY: [WorkItemStatus.IN_PROGRESS],
        WorkItemStatus.IN_PROGRESS: [WorkItemStatus.WAITING_PARTS, WorkItemStatus.READY],
        WorkItemStatus.WAITING_PARTS: [WorkItemStatus.IN_PROGRESS, WorkItemStatus.READY],
        WorkItemStatus.READY: [],
    }


@pytest.mark.parametrize("status", list(WorkItemStatus))
def test_work_item_schemas_expose_flow(status):
    common = dict(id=uuid.uuid4(), visit_id=uuid.uuid4(), name="Замена масла", status=status,
                  free_text_name=None, catalog_item_id=None)
    expected = [s.value for s in WORK_ITEM_NEXT_STATUSES[status]]
    item = WorkItemOut(**common, approved_by_client=False, assigned_mechanic_id=None)
    mine = WorkItemMineOut(**common)
    assert item.model_dump(mode="json")["allowed_next_statuses"] == expected
    assert mine.model_dump(mode="json")["allowed_next_statuses"] == expected
