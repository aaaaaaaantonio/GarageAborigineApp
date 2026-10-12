"""MVP next-step flow for work items — a UI hint only.

The API still accepts any work-item status on PATCH; clients (bot, web) offer
these steps so no client keeps its own copy of the flow.
"""
from app.core.enums import WorkItemStatus

WORK_ITEM_NEXT_STATUSES: dict[WorkItemStatus, list[WorkItemStatus]] = {
    WorkItemStatus.NOT_READY: [WorkItemStatus.IN_PROGRESS],
    WorkItemStatus.IN_PROGRESS: [WorkItemStatus.WAITING_PARTS, WorkItemStatus.READY],
    WorkItemStatus.WAITING_PARTS: [WorkItemStatus.IN_PROGRESS, WorkItemStatus.READY],
    WorkItemStatus.READY: [],
}
