import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import type { Visit } from '../api/types';
import { makeVisit, mockVisitPage } from '../test/fixtures';
import { renderApp } from '../test/render';
import { server } from '../test/server';

const visits = [
  makeVisit({ id: 'v1', plate_number: 'А123ВС77', status: 'in_progress', assigned_master_id: 'u-master' }),
  makeVisit({ id: 'v2', plate_number: 'Х777ХХ99', make_model: 'Kia Rio', status: 'waiting_parts', assigned_master_id: 'u-other', master_name: 'Другой' }),
];

/** Serves `items` and records every query string the screen asks for. */
function serveVisits(items: Visit[] = visits) {
  const queries: URLSearchParams[] = [];
  server.use(
    http.get('/api/visits', ({ request }) => {
      queries.push(new URL(request.url).searchParams);
      return HttpResponse.json({ items, has_more: false, total_count: items.length, issued_amount: 0 });
    }),
  );
  return queries;
}

const last = (queries: URLSearchParams[]) => queries[queries.length - 1];

test('lists active visits as cards', async () => {
  const queries = serveVisits();
  renderApp('/visits', { as: 'master' });
  expect(await screen.findByLabelText('Госномер А123ВС77')).toBeInTheDocument();
  expect(screen.getByLabelText('Госномер Х777ХХ99')).toBeInTheDocument();
  expect(screen.getByText('Ждём запчасти')).toBeInTheDocument();
  expect(last(queries).get('active')).toBe('true');
  expect(last(queries).get('sort')).toBe('date');
});

test.each([
  ['mine', 'Мои', 'master_id', 'u-master'],
  ['approval', 'Согласование', 'status', 'approval'],
  ['parts', 'Ждут запчасти', 'status', 'waiting_parts'],
  ['ready', 'Готовы', 'status', 'ready'],
  ['unassigned', 'Без механика', 'unassigned_work', 'true'],
  ['stale', 'Долго стоят', 'stale', 'true'],
])('filter %s (%s) asks the server for %s=%s', async (option, label, key, value) => {
  const queries = serveVisits();
  const { user } = renderApp('/visits', { as: 'master' });
  await screen.findByLabelText('Госномер А123ВС77');
  const select = screen.getByLabelText('Фильтр');
  expect(within(select).getByRole('option', { name: label })).toBeInTheDocument();
  await user.selectOptions(select, option);
  await waitFor(() => expect(last(queries).get(key)).toBe(value));
  expect(select).toHaveValue(option);
});

test('sort select changes the sort param', async () => {
  const queries = serveVisits();
  const { user } = renderApp('/visits', { as: 'master' });
  await screen.findByLabelText('Госномер А123ВС77');
  await user.selectOptions(screen.getByLabelText('Сортировка'), 'stale');
  await waitFor(() => expect(last(queries).get('sort')).toBe('stale'));
});

test('admin picks a master, master does not see the picker or a "mine" chip for admin', async () => {
  const queries = serveVisits();
  server.use(http.get('/api/users/masters', () => HttpResponse.json([
    { id: 'm1', role: 'master', full_name: 'Кузнецов', telegram_id: null, phone: null, branch_id: 'b1' },
  ])));
  const { user } = renderApp('/visits', { as: 'admin' });
  await screen.findByLabelText('Госномер А123ВС77');
  expect(within(screen.getByLabelText('Фильтр')).queryByRole('option', { name: 'Мои' })).not.toBeInTheDocument();
  await user.selectOptions(await screen.findByLabelText('Мастер'), 'm1');
  await waitFor(() => expect(last(queries).get('master_id')).toBe('m1'));
});

test('master has no master picker', async () => {
  serveVisits();
  renderApp('/visits', { as: 'master' });
  await screen.findByLabelText('Госномер А123ВС77');
  expect(screen.queryByLabelText('Мастер')).not.toBeInTheDocument();
});

test('card shows how long the visit sits in its status', async () => {
  const fourDaysAgo = new Date(Date.now() - 4 * 86_400_000 - 3_600_000).toISOString();
  serveVisits([makeVisit({ status_changed_at: fourDaysAgo }), makeVisit({ id: 'v3', plate_number: 'О001ОО77', status_changed_at: new Date().toISOString() })]);
  renderApp('/visits', { as: 'master' });
  expect(await screen.findByText('4 дн. в статусе')).toBeInTheDocument();
  expect(screen.getAllByText(/дн\. в статусе/)).toHaveLength(1);
});

test('links to the work board and the archive', async () => {
  serveVisits();
  renderApp('/visits', { as: 'master' });
  expect(await screen.findByRole('link', { name: 'Доска работ' })).toHaveAttribute('href', '/works');
  expect(screen.getByRole('link', { name: 'Архив' })).toHaveAttribute('href', '/visits/archive');
});

test('empty list offers a new visit', async () => {
  serveVisits([]);
  renderApp('/visits', { as: 'master' });
  const empty = await screen.findByText('Нет заездов в работе');
  expect(within(empty.parentElement!).getByRole('link', { name: '+ Новый заезд' })).toHaveAttribute('href', '/visits/new');
});

test('empty filter result says so', async () => {
  serveVisits([]);
  const { user } = renderApp('/visits', { as: 'master' });
  await screen.findByText('Нет заездов в работе');
  await user.selectOptions(screen.getByLabelText('Фильтр'), 'ready');
  expect(await screen.findByText('Нет заездов с этим фильтром')).toBeInTheDocument();
});

test('card opens the visit', async () => {
  serveVisits();
  mockVisitPage();
  const { user } = renderApp('/visits', { as: 'master' });
  await user.click(await screen.findByLabelText('Госномер А123ВС77'));
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/visits/v1'));
});
