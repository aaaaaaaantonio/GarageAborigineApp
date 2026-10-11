import { http, HttpResponse } from 'msw';
import { server } from '../test/server';
import { getToken, setToken } from '../auth/token';
import { ApiError, api, onUnauthorized, parseErrorBody } from './client';

test('sends bearer token and returns json', async () => {
  setToken('tok-1');
  server.use(
    http.get('/api/visits', ({ request }) =>
      HttpResponse.json({ auth: request.headers.get('Authorization') }),
    ),
  );
  expect(await api.get('/visits')).toEqual({ auth: 'Bearer tok-1' });
});

test('401 clears token and calls the unauthorized handler', async () => {
  setToken('tok-1');
  const handler = vi.fn();
  onUnauthorized(handler);
  server.use(http.get('/api/visits', () => HttpResponse.json({ detail: 'Invalid session token' }, { status: 401 })));
  await expect(api.get('/visits')).rejects.toMatchObject({ status: 401 });
  expect(getToken()).toBeNull();
  expect(handler).toHaveBeenCalledOnce();
});

test('parses 422 field errors and strips the pydantic prefix', async () => {
  server.use(
    http.post('/api/clients', () =>
      HttpResponse.json(
        { detail: [{ loc: ['body', 'phone'], msg: 'Value error, Неверный формат телефона', type: 'value_error' }] },
        { status: 422 },
      ),
    ),
  );
  const err = (await api.post('/clients', {}).catch((e) => e)) as ApiError;
  expect(err).toBeInstanceOf(ApiError);
  expect(err.status).toBe(422);
  expect(err.fields).toEqual({ phone: 'Неверный формат телефона' });
  expect(err.message).toBe('Неверный формат телефона');
});

test('409 keeps the detail text', async () => {
  server.use(http.post('/api/vehicles', () => HttpResponse.json({ detail: 'Машина с таким VIN уже есть' }, { status: 409 })));
  await expect(api.post('/vehicles', {})).rejects.toMatchObject({ status: 409, message: 'Машина с таким VIN уже есть' });
});

test('network failure is status 0 with a readable message', async () => {
  server.use(http.get('/api/visits', () => HttpResponse.error()));
  await expect(api.get('/visits')).rejects.toMatchObject({ status: 0, message: 'Нет связи с сервером' });
});

test('5xx reads as no connection, not as a server detail', async () => {
  server.use(http.get('/api/visits', () => HttpResponse.text('boom', { status: 502 })));
  await expect(api.get('/visits')).rejects.toMatchObject({ status: 502, message: 'Нет связи с сервером' });
});

test('model-level 422 without a field becomes a general message', () => {
  expect(parseErrorBody({ detail: [{ loc: ['body'], msg: 'Value error, Укажите ровно одно' }] })).toEqual({
    message: 'Укажите ровно одно',
    fields: {},
  });
});
