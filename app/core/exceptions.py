class MileageRollbackNotConfirmed(Exception):
    """Пробег при приёме меньше последнего зафиксированного, а флаг ручного
    подтверждения не установлен."""


class InvalidAssignedMaster(Exception):
    """assigned_master_id не ссылается на активного пользователя с ролью MASTER."""
