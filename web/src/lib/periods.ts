export type Period = 'week' | 'month' | 'quarter' | 'all';

const DAYS: Record<Exclude<Period, 'all'>, number> = { week: 7, month: 30, quarter: 90 };

export const PERIOD_LABELS: Record<Period, string> = { week: 'Неделя', month: 'Месяц', quarter: 'Квартал', all: 'Всё' };

/** Start of the period as ISO; `all` has no start. */
export function sinceFor(period: Period, now: Date = new Date()): string | undefined {
  if (period === 'all') return undefined;
  return new Date(now.getTime() - DAYS[period] * 86_400_000).toISOString();
}
