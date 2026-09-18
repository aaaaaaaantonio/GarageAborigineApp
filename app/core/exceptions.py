class MileageRollbackNotConfirmed(Exception):
    """Пробег при приёме меньше последнего зафиксированного, а флаг ручного
    подтверждения не установлен."""


class InvalidAssignedMaster(Exception):
    """assigned_master_id не ссылается на активного пользователя с ролью MASTER."""


class NotAssignedMechanic(Exception):
    """Механик пытается изменить статус работы, назначенной не на него."""


class MissingWorkNameSource(Exception):
    """Ни catalog_item_id, ни free_text_name не указаны."""


class InvalidTransition(Exception):
    """Переход между статусами заезда не разрешён FSM."""


class CancelReasonRequired(Exception):
    """Отмена заезда требует непустой причины."""


class NotAllWorkItemsReady(Exception):
    """Переход в 'Готов' требует, чтобы все работы были в статусе 'ready'."""


class DraftNotFound(Exception):
    """Черновик согласия по токену не найден."""


class DraftExpired(Exception):
    """Токен черновика согласия истёк (TTL 10-15 минут)."""
