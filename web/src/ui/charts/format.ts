import type { StatsUnit } from '../../api/types';

const oneDecimal = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 });
const plain = (n: number) => oneDecimal.format(n).replace(/[  ]/g, ' ');

export function formatValue(value: number | string, unit: StatsUnit): string {
  if (typeof value === 'string') return value;
  switch (unit) {
    case 'rub': return `${plain(Math.round(value))} ₽`;
    case 'hours': return `${plain(value)} н/ч`;
    case 'days': return `${plain(value)} дн.`;
    case 'pct': return `${plain(value)} %`;
    default: return plain(value);
  }
}

/**
 * Axis tick. Roubles switch to thousands («15 тыс») only on axes reaching 10 000 ₽,
 * so one axis never mixes «833» with «1,7 т».
 */
export function formatTick(value: number, unit: StatsUnit, max: number): string {
  return unit === 'rub' && max >= 10000 ? `${plain(value / 1000)} тыс` : plain(value);
}

/**
 * Axis top for a chart, three tick steps: each step is 1, 2, 2,5 or 5 × 10ⁿ, so ticks are round.
 * Counts additionally keep whole-number steps.
 */
export function axisMax(v: number, unit: StatsUnit): number {
  if (unit === 'count') return Math.max(3, Math.ceil(niceMax(v) / 3) * 3);
  if (v <= 0) return 3;
  const third = v / 3;
  const p = 10 ** Math.floor(Math.log10(third));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * p).find((s) => s >= third)!;
  return step * 3;
}

/** Accessible description of a chart's data: «title: label — value; …». */
export function describe(title: string, labels: string[], values: (i: number) => string): string {
  return `${title}: ${labels.map((l, i) => `${l} — ${values(i)}`).join('; ')}`;
}

/** Round axis top just above `v`, so ticks land on readable numbers. */
export function niceMax(v: number): number {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  for (const m of [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}
