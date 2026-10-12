import { formatDate, formatKm, formatRub } from './format';
import { WORK_STATUS_ICONS } from './labels';
import { homePath } from './roles';
import { isValidPhone, isValidVin, looksLikePlate, normalizePlate, normalizeVin } from './validators';

test.each(['+7 (999) 123-45-67', '89991234567', '9991234567'])('valid phone %s', (raw) => {
  expect(isValidPhone(raw)).toBe(true);
});
test.each(['', '123', '+380 99 123 45 67', '799912345678', 'Иванов'])('invalid phone %s', (raw) => {
  expect(isValidPhone(raw)).toBe(false);
});
test.each(['JTDBR32E720012345', 'jtdbr32e 720012345', 'GX110-6012345'])('valid vin %s', (raw) => {
  expect(isValidVin(raw)).toBe(true);
});
test.each(['', 'ABC12', 'JTDBR32E72001234O', 'А123ВС77', 'ABCDEFG'])('invalid vin %s', (raw) => {
  expect(isValidVin(raw)).toBe(false);
});
test('normalizeVin', () => expect(normalizeVin(' gx110-6012345 ')).toBe('GX110-6012345'));
test.each(['А123ВС77', 'а 123 вс 777', 'A123BC77', 'Х000ХХ-99'])('plate %s', (raw) => {
  expect(looksLikePlate(raw)).toBe(true);
});
test.each(['JTDBR32E720012345', 'GX110-6012345', 'А123', 'Иванов'])('not plate %s', (raw) => {
  expect(looksLikePlate(raw)).toBe(false);
});
test('normalizePlate', () => {
  expect(normalizePlate('а 123 вс-77')).toBe('А123ВС77');
  expect(normalizePlate('a123bc77')).toBe('А123ВС77');
});
test('format', () => {
  expect(formatRub(9850)).toBe('9 850 ₽');
  expect(formatRub(1200.5)).toBe('1 200,5 ₽');
  expect(formatKm(120500)).toBe('120 500 км');
  expect(formatDate('2026-10-10T09:30:00Z')).toBe('10.10.2026');
});
test('formatDate shows the local calendar date', () => {
  vi.stubEnv('TZ', 'Europe/Moscow'); // UTC+3: 22:30Z is already the next day
  try {
    expect(formatDate('2026-10-10T22:30:00Z')).toBe('11.10.2026');
  } finally {
    vi.unstubAllEnvs();
  }
});
test('labels and roles', () => {
  expect(WORK_STATUS_ICONS.waiting_parts).toBe('📦');
  expect(homePath('mechanic')).toBe('/my');
  expect(homePath('master')).toBe('/visits');
});
