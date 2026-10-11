import { ApiError } from '../api/client';

export interface FormErrors {
  fields: Record<string, string>;
  general: string;
}

export const NO_ERRORS: FormErrors = { fields: {}, general: '' };

export function toFormErrors(error: unknown, known: string[], conflictField?: string): FormErrors {
  if (!(error instanceof ApiError)) return { fields: {}, general: 'Ошибка' };
  if (error.status === 409 && conflictField) return { fields: { [conflictField]: error.message }, general: '' };
  const fields: Record<string, string> = {};
  const other: string[] = [];
  for (const [key, msg] of Object.entries(error.fields)) {
    if (known.includes(key)) fields[key] = msg;
    else other.push(msg);
  }
  const general = Object.keys(fields).length === 0 ? error.message : other.join('; ');
  return { fields, general };
}
