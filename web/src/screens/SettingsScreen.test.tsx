import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { renderApp } from '../test/render';
import { server } from '../test/server';

const OFF = { mechanic_sees_prices: false, mechanic_sees_client_name: false, mechanic_sees_client_phone: false, mechanic_sees_vin: false };

function serveSettings(pay = [{ user_id: 'm1', full_name: 'Морозов', pay_scheme: null, pay_value: null }]) {
  server.use(
    http.get('/api/settings', () => HttpResponse.json(OFF)),
    http.get('/api/settings/pay', () => HttpResponse.json(pay)),
  );
}

test('admin switches what mechanics see', async () => {
  serveSettings();
  let body: unknown = null;
  server.use(http.patch('/api/settings', async ({ request }) => {
    body = await request.json();
    return HttpResponse.json({ ...OFF, mechanic_sees_prices: true });
  }));
  const { user } = renderApp('/settings', { as: 'admin' });
  const prices = await screen.findByRole('switch', { name: 'Цены и заработок' });
  expect(prices).not.toBeChecked();
  expect(screen.getByRole('switch', { name: 'Телефон клиента' })).toBeInTheDocument();
  await user.click(prices);
  await waitFor(() => expect(body).toEqual({ mechanic_sees_prices: true }));
});

test('admin sets a percent scheme, comma decimals accepted', async () => {
  serveSettings();
  let body: unknown = null;
  server.use(http.patch('/api/settings/pay/m1', async ({ request }) => {
    body = await request.json();
    return HttpResponse.json({ user_id: 'm1', full_name: 'Морозов', pay_scheme: 'percent', pay_value: 12.5 });
  }));
  const { user } = renderApp('/settings', { as: 'admin' });
  const card = (await screen.findByText('Морозов')).closest('.card') as HTMLElement;
  expect(within(card).queryByLabelText('Процент, %')).not.toBeInTheDocument();
  await user.selectOptions(within(card).getByLabelText('Схема оплаты'), 'percent');
  await user.type(within(card).getByLabelText('Процент, %'), '12,5');
  await user.click(within(card).getByRole('button', { name: 'Сохранить' }));
  await waitFor(() => expect(body).toEqual({ pay_scheme: 'percent', pay_value: 12.5 }));
});

test('full cost needs no number', async () => {
  serveSettings();
  let body: unknown = null;
  server.use(http.patch('/api/settings/pay/m1', async ({ request }) => {
    body = await request.json();
    return HttpResponse.json({ user_id: 'm1', full_name: 'Морозов', pay_scheme: 'full', pay_value: null });
  }));
  const { user } = renderApp('/settings', { as: 'admin' });
  const card = (await screen.findByText('Морозов')).closest('.card') as HTMLElement;
  await user.selectOptions(within(card).getByLabelText('Схема оплаты'), 'full');
  expect(within(card).queryByLabelText(/Ставка|Процент/)).not.toBeInTheDocument();
  await user.click(within(card).getByRole('button', { name: 'Сохранить' }));
  await waitFor(() => expect(body).toEqual({ pay_scheme: 'full', pay_value: null }));
});

test('«Ещё» has «Настройки» for the admin only', async () => {
  renderApp('/more', { as: 'admin' });
  expect(await screen.findByRole('link', { name: 'Настройки' })).toHaveAttribute('href', '/settings');
});

test('a master has no «Настройки»', async () => {
  renderApp('/more', { as: 'master' });
  await screen.findByRole('link', { name: 'Статистика' });
  expect(screen.queryByRole('link', { name: 'Настройки' })).not.toBeInTheDocument();
});
