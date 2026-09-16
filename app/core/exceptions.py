class MileageRollbackNotConfirmed(Exception):
    """Пробег при приёме меньше последнего зафиксированного, а флаг ручного
    подтверждения не установлен."""


class InvalidAssignedMaster(Exception):
    """assigned_master_id не ссылается на активного пользователя с ролью MASTER."""


class NotAssignedMechanic(Exception):
    """Механик пытается изменить статус работы, назначенной не на него."""


class MissingWorkNameSource(Exception):
    """Ни catalog_item_id, ни free_text_name не указаны."""
