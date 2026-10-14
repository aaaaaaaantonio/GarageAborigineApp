import type { Role, VisitStatus, WorkCategory, WorkItemStatus } from '../api/types';

export const VISIT_STATUS_LABELS: Record<VisitStatus, string> = {
  received: 'Принят',
  diagnostics: 'Диагностика',
  approval: 'Согласование',
  in_progress: 'Ремонт',
  waiting_parts: 'Ждём запчасти',
  ready: 'Готов',
  issued: 'Выдан',
  cancelled: 'Отменён',
};

export const WORK_STATUS_LABELS: Record<WorkItemStatus, string> = {
  not_ready: 'Не начата',
  in_progress: 'В работе',
  waiting_parts: 'Ждёт запчасти',
  ready: 'Готово',
};

export const WORK_STATUS_ICONS: Record<WorkItemStatus, string> = {
  not_ready: '⏳',
  in_progress: '🔧',
  waiting_parts: '📦',
  ready: '✅',
};

export const ROLE_LABELS: Record<Role, string> = { admin: 'Админ', master: 'Мастер', mechanic: 'Механик' };

/** Name in assignee pickers; admins can take work too and are marked as such. */
export function assigneeLabel(user: { full_name: string; role: Role }): string {
  return user.role === 'admin' ? `${user.full_name} (админ)` : user.full_name;
}

export const WORK_CATEGORY_LABELS: Record<WorkCategory, string> = {
  diagnostics: 'Диагностика',
  maintenance: 'ТО',
  body: 'Кузовные',
  electrical: 'Электрика',
  chassis: 'Ходовая',
  other: 'Прочее',
};

/** What to pick up first: in hand, not started, blocked, done (same order as the API's `urgency`). */
export const WORK_URGENCY: WorkItemStatus[] = ['in_progress', 'not_ready', 'waiting_parts', 'ready'];

export function byUrgency<T extends { status: WorkItemStatus }>(items: T[]): T[] {
  return [...items].sort((a, b) => WORK_URGENCY.indexOf(a.status) - WORK_URGENCY.indexOf(b.status));
}
