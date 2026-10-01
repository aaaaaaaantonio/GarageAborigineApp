class MileageRollbackNotConfirmed(Exception):
    """Пробег при приёме меньше последнего зафиксированного, а флаг ручного
    подтверждения не установлен."""


class InvalidAssignedMaster(Exception):
    """assigned_master_id не ссылается на активного пользователя с ролью MASTER."""


class ClientPhoneTaken(Exception):
    """Телефон уже принадлежит активному (не удалённому) клиенту."""


class InvalidAssignedMechanic(Exception):
    """assigned_mechanic_id не ссылается на активного пользователя с ролью MECHANIC."""


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


class DraftAlreadyUsed(Exception):
    """Черновик согласия уже был подтверждён ранее (повторное использование токена)."""


class VisitNotFound(Exception):
    """Заезд с указанным id не найден."""


class VehicleNotFound(Exception):
    """Автомобиль с указанным id не найден."""


class WorkItemNotFound(Exception):
    """Работа в заезде с указанным id не найдена."""


class DocumentNotFound(Exception):
    """Документ по заезду ещё не сформирован или файл отсутствует."""
