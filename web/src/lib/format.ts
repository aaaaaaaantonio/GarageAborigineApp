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
  const dd = String(d.getUTCDate()).padStart(2, '0');
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
  return `${dd}.${mm}.${d.getUTCFullYear()}`;
}

export function parseNumber(raw: string): number | null {
  const text = raw.trim().replace(',', '.');
  if (!text) return null;
  const n = Number(text);
  return Number.isFinite(n) ? n : null;
}
