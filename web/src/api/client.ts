import { clearToken, getToken } from '../auth/token';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public fields: Record<string, string> = {},
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

const NO_CONNECTION = 'Нет связи с сервером';
const DEFAULT_TEXT: Record<number, string> = {
  401: 'Требуется вход',
  403: 'Недостаточно прав',
  404: 'Не найдено',
  409: 'Конфликт',
  422: 'Некорректные данные',
};

let unauthorizedHandler: () => void = () => {};

export function onUnauthorized(handler: () => void): void {
  unauthorizedHandler = handler;
}

interface ValidationIssue {
  loc?: (string | number)[];
  msg?: string;
}

export function parseErrorBody(body: unknown): { message: string; fields: Record<string, string> } {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === 'string') return { message: detail, fields: {} };
  if (!Array.isArray(detail)) return { message: '', fields: {} };
  const fields: Record<string, string> = {};
  const messages: string[] = [];
  for (const issue of detail as ValidationIssue[]) {
    const msg = (issue.msg ?? '').replace(/^Value error, /, '');
    const key = [...(issue.loc ?? [])].reverse().find((p) => typeof p === 'string' && p !== 'body');
    if (typeof key === 'string' && !(key in fields)) fields[key] = msg;
    if (msg) messages.push(msg);
  }
  return { message: messages.join('; '), fields };
}

async function send(method: string, path: string, body?: unknown): Promise<Response> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let res: Response;
  try {
    res = await fetch(`${window.location.origin}/api${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, NO_CONNECTION);
  }
  if (res.ok) return res;
  if (res.status === 401) {
    clearToken();
    unauthorizedHandler();
  }
  if (res.status >= 500) throw new ApiError(res.status, NO_CONNECTION);
  let parsed: { message: string; fields: Record<string, string> } = { message: '', fields: {} };
  try {
    parsed = parseErrorBody(await res.json());
  } catch {
    // not JSON
  }
  throw new ApiError(res.status, parsed.message || DEFAULT_TEXT[res.status] || 'Ошибка', parsed.fields);
}

export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await send(method, path, body);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body: unknown = {}) => request<T>('POST', path, body),
  patch: <T>(path: string, body: unknown = {}) => request<T>('PATCH', path, body),
};
