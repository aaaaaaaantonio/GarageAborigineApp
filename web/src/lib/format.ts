// Intl ru-RU groups digits with U+00A0 or U+202F; normalise to a plain space.
const GROUP_SPACE = /[  ]/g;
const number = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 });

export function formatRub(n: number): string {
  return `${number.format(n).replace(GROUP_SPACE, ' ')} ₽`;
}

export function formatKm(n: number): string {
  return `${number.format(n).replace(GROUP_SPACE, ' ')} км`;
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  return `${dd}.${mm}.${d.getFullYear()}`;
}

export function parseNumber(raw: string): number | null {
  const text = raw.trim().replace(',', '.');
  if (!text) return null;
  const n = Number(text);
  return Number.isFinite(n) ? n : null;
}

/** Whole days from `iso` to `now` (0 for less than a day). */
export function daysSince(iso: string, now: number = Date.now()): number {
  return Math.max(0, Math.floor((now - new Date(iso).getTime()) / 86_400_000));
}

export function formatHours(n: number): string {
  return `${number.format(n).replace(GROUP_SPACE, ' ')} н/ч`;
}
