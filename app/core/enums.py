import enum


class ClientType(str, enum.Enum):
    INDIVIDUAL = "individual"
    LEGAL = "legal"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MASTER = "master"
    MECHANIC = "mechanic"


class VisitStatus(str, enum.Enum):
    RECEIVED = "received"
    DIAGNOSTICS = "diagnostics"
    APPROVAL = "approval"
    IN_PROGRESS = "in_progress"
    WAITING_PARTS = "waiting_parts"
    READY = "ready"
    ISSUED = "issued"
    CANCELLED = "cancelled"


class WorkItemStatus(str, enum.Enum):
    NOT_READY = "not_ready"
    IN_PROGRESS = "in_progress"
    WAITING_PARTS = "waiting_parts"
    READY = "ready"


class WorkCategory(str, enum.Enum):
    DIAGNOSTICS = "diagnostics"
    MAINTENANCE = "maintenance"
    BODY = "body"
    ELECTRICAL = "electrical"
    CHASSIS = "chassis"
    OTHER = "other"


class PartAvailability(str, enum.Enum):
    IN_STOCK = "in_stock"
    ORDERED = "ordered"
    PENDING = "pending"


class ConsentMethod(str, enum.Enum):
    QR_ONSITE = "qr_onsite"
    PAPER = "paper"
    TELEGRAM_BOT_START = "telegram_bot_start"
    EMAIL_CONFIRMATION = "email_confirmation"
    SMS_OTP = "sms_otp"


class ApprovedVia(str, enum.Enum):
    CRM_STATUS = "crm_status"
    BOT = "bot"
