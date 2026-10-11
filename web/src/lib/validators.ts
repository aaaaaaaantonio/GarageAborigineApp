// Same rules as bot/validators.py and app/core/{phone,vin,plate}.py — the API has the final say.
export const PHONE_FORMAT_ERROR = 'Неверный формат телефона. Пример: +7 900 123-45-67';
export const VIN_FORMAT_ERROR =
  'Неверный формат VIN: 17 символов (латиница и цифры без I, O, Q) или номер кузова, например GX110-6012345';
export const PLATE_FORMAT_ERROR = 'Неверный госномер. Пример: А123ВС77';

const VIN_RE = /^[A-HJ-NPR-Z0-9]{17}$/;
const FRAME_RE = /^(?=.*\d)[A-Z0-9]+(-[A-Z0-9]+)*$/;
const PLATE_LETTERS = 'АВЕКМНОРСТУХ';
const PLATE_RE = new RegExp(`^[${PLATE_LETTERS}]\\d{3}[${PLATE_LETTERS}]{2}\\d{2,3}$`);
const LATIN = 'ABEKMHOPCTYX';

export function normalizePhone(raw: string): string {
  let digits = raw.replace(/\D/g, '');
  if (digits.length === 11 && digits[0] === '8') digits = '7' + digits.slice(1);
  if (digits.length === 10) digits = '7' + digits;
  return digits;
}

export function isValidPhone(raw: string): boolean {
  const digits = normalizePhone(raw);
  return digits.length === 11 && digits[0] === '7';
}

export function normalizeVin(raw: string): string {
  return raw.replace(/\s/g, '').toUpperCase();
}

export function isValidVin(raw: string): boolean {
  const vin = normalizeVin(raw);
  if (vin.length === 17 && !vin.includes('-')) return VIN_RE.test(vin);
  return vin.length >= 6 && vin.length <= 17 && FRAME_RE.test(vin);
}

export function normalizePlate(raw: string): string {
  return [...raw.replace(/[\s-]/g, '').toUpperCase()]
    .map((ch) => {
      const i = LATIN.indexOf(ch);
      return i === -1 ? ch : PLATE_LETTERS[i];
    })
    .join('');
}

export function looksLikePlate(raw: string): boolean {
  return PLATE_RE.test(normalizePlate(raw));
}
