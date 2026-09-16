from app.core.enums import VisitStatus

ALLOWED_TRANSITIONS: dict[VisitStatus, set[VisitStatus]] = {
    VisitStatus.RECEIVED: {VisitStatus.DIAGNOSTICS, VisitStatus.CANCELLED},
    VisitStatus.DIAGNOSTICS: {VisitStatus.APPROVAL, VisitStatus.CANCELLED},
    VisitStatus.APPROVAL: {VisitStatus.IN_PROGRESS, VisitStatus.CANCELLED},
    VisitStatus.IN_PROGRESS: {VisitStatus.WAITING_PARTS, VisitStatus.READY, VisitStatus.CANCELLED},
    VisitStatus.WAITING_PARTS: {VisitStatus.IN_PROGRESS, VisitStatus.CANCELLED},
    VisitStatus.READY: {VisitStatus.ISSUED, VisitStatus.CANCELLED},
    VisitStatus.ISSUED: set(),
    VisitStatus.CANCELLED: set(),
}
