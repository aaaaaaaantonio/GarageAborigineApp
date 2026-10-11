import { act, screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { api } from '../api/client';
import { getToken, setToken } from './token';
import { server } from '../test/server';
import { USERS, renderApp } from '../test/render';

test('browser without token shows dev login and signs in as the picked user', async () => {
  server.use(
    http.get('/api/auth/dev-users', () => HttpResponse.json([USERS.master, USERS.mechanic])),
    http.post('/api/auth/dev-login', async ({ request }) => {
      const { user_id } = (await request.json()) as { user_id: string };
      const user = Object.values(USERS).find((u) => u.id === user_id)!;
      return HttpResponse.json({ token: 'tok-mech', user });
    }),
  );
  const { user } = renderApp('/');
  await user.click(await screen.findByRole('button', { name: /Сидоров Иван/ }));
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/my'));
  expect(getToken()).toBe('tok-mech');
});

test('dev login disabled tells to open from Telegram', async () => {
  server.use(http.get('/api/auth/dev-users', () => HttpResponse.json({ detail: 'Not Found' }, { status: 404 })));
  renderApp('/visits');
  expect(await screen.findByText('Откройте приложение из Telegram')).toBeInTheDocument();
});

test('mini app signs in with initData automatically', async () => {
  const webApp = {
    initData: 'query_id=1&hash=abc', ready: vi.fn(), expand: vi.fn(),
    BackButton: { show: vi.fn(), hide: vi.fn(), onClick: vi.fn(), offClick: vi.fn() },
  };
  (window as { Telegram?: unknown }).Telegram = { WebApp: webApp };
  let sent = '';
  server.use(
    http.post('/api/auth/telegram', async ({ request }) => {
      sent = ((await request.json()) as { init_data: string }).init_data;
      return HttpResponse.json({ token: 'tok-tg', user: USERS.master });
    }),
  );
  renderApp('/visits');
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/visits'));
  expect(sent).toBe('query_id=1&hash=abc');
});

test('mini app non-staff sees the refusal', async () => {
  (window as { Telegram?: unknown }).Telegram = {
    WebApp: { initData: 'x', ready: vi.fn(), expand: vi.fn(), BackButton: { show: vi.fn(), hide: vi.fn(), onClick: vi.fn(), offClick: vi.fn() } },
  };
  server.use(http.post('/api/auth/telegram', () => HttpResponse.json({ detail: 'Вы не сотрудник сервиса' }, { status: 403 })));
  renderApp('/');
  expect(await screen.findByText('Вы не сотрудник сервиса')).toBeInTheDocument();
});

test('stored token is checked with /auth/me and lands on the role home', async () => {
  renderApp('/', { as: 'master' });
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/visits'));
  expect(screen.getByRole('link', { name: /Заезды/ })).toBeInTheDocument();
});

test('mechanic tab bar has only my works and search', async () => {
  renderApp('/my', { as: 'mechanic' });
  expect(await screen.findByRole('link', { name: /Мои работы/ })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Поиск/ })).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: /Заезды/ })).not.toBeInTheDocument();
});

test('RoleGate shows no access for mechanic on a master route', async () => {
  renderApp('/more', { as: 'mechanic' });
  expect(await screen.findByText('Нет доступа к этому разделу')).toBeInTheDocument();
});

test('RequireAuth redirects to login after 401', async () => {
  server.use(
    http.get('/api/auth/dev-users', () => HttpResponse.json([USERS.master])),
    http.get('/api/visits', () => HttpResponse.json({ detail: 'Invalid session token' }, { status: 401 })),
  );
  renderApp('/more', { as: 'master' });
  await screen.findByRole('link', { name: /Заезды/ });
  await act(async () => {
    await api.get('/visits').catch(() => {});
  });
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/login'));
  expect(getToken()).toBeNull();
});

test('stored but rejected token falls back to login', async () => {
  setToken('stale');
  server.use(
    http.get('/api/auth/me', () => HttpResponse.json({ detail: 'Invalid session token' }, { status: 401 })),
    http.get('/api/auth/dev-users', () => HttpResponse.json([USERS.master])),
  );
  renderApp('/visits');
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/login'));
  expect(getToken()).toBeNull();
});
