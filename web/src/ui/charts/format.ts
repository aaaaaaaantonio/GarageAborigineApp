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

/** Axis tick: roubles in thousands («15 т»), the rest as plain numbers. */
export function formatTick(value: number, unit: StatsUnit): string {
  return unit === 'rub' && value >= 1000 ? `${plain(value / 1000)} т` : plain(value);
}

/** Axis top for a chart: counts get a multiple of 3 so the three tick steps are whole numbers. */
export function axisMax(v: number, unit: StatsUnit): number {
  const n = niceMax(v);
  return unit === 'count' ? Math.max(3, Math.ceil(n / 3) * 3) : n;
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
