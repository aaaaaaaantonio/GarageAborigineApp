import { screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import type { Stats } from '../api/types';
import { USERS, renderApp } from '../test/render';
import { server } from '../test/server';

const STATS: Stats = {
  section: 'money', period: 'month',
  kpis: [{ key: 'revenue', label: 'Выручка', value: 20000, unit: 'rub', delta_pct: 150, compare: true }],
  charts: [{ key: 'revenue', kind: 'bars', title: 'Выручка по неделям', sub: null, unit: 'rub', labels: ['a', 'b'],
    series: [{ name: 'Выручка', values: [1000, 2000] }] }],
};

function serve() {
  const urls: string[] = [];
  server.use(
    http.get('/api/stats/:section', ({ request }) => {
      urls.push(new URL(request.url).pathname + new URL(request.url).search);
      return HttpResponse.json(STATS);
    }),
    http.get('/api/users/masters', () => HttpResponse.json([USERS.master])),
  );
  return urls;
}

test('admin: sections, period and master filters drive the request', async () => {
  const urls = serve();
  const { user } = renderApp('/stats', { as: 'admin' });
  expect(await screen.findByText('▲ 150% к прошлому периоду')).toBeInTheDocument();
  expect(urls[0]).toBe('/api/stats/money?period=month');
  await user.click(screen.getByRole('tab', { name: 'Поток' }));
  await waitFor(() => expect(urls.at(-1)).toBe('/api/stats/flow?period=month'));
  await user.selectOptions(screen.getByLabelText('Период'), 'year');
  await waitFor(() => expect(urls.at(-1)).toBe('/api/stats/flow?period=year'));
  await user.selectOptions(await screen.findByLabelText('Мастер'), 'u-master');
  await waitFor(() => expect(urls.at(-1)).toBe('/api/stats/flow?period=year&master_id=u-master'));
});

test('mechanic: own stats, no sections and no master filter', async () => {
  const urls = serve();
  renderApp('/stats', { as: 'mechanic' });
  expect(await screen.findByText('Выручка по неделям')).toBeInTheDocument();
  expect(urls[0]).toBe('/api/stats/mine?period=month');
  expect(screen.queryByRole('tab')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('Мастер')).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Статистика/ })).toHaveAttribute('href', '/stats');
});

test('master and admin reach stats from «Ещё»', async () => {
  serve();
  renderApp('/more', { as: 'master' });
  expect(await screen.findByRole('link', { name: 'Статистика' })).toHaveAttribute('href', '/stats');
});
