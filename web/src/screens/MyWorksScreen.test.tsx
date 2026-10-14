import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse, type JsonBodyType } from 'msw';
import { doneList, makeDoneWork, makeMyWork } from '../test/fixtures';
import { renderApp } from '../test/render';
import { server } from '../test/server';

test('lists assigned works linking to the work screen', async () => {
  server.use(http.get('/api/work-items/mine', () => HttpResponse.json([makeMyWork(), makeMyWork({ id: 'w2', name: 'Диагностика подвески', plate_number: null, make_model: null })])));
  renderApp('/my', { as: 'mechanic' });
  const link = await screen.findByRole('link', { name: /Замена масла ДВС/ });
  expect(link).toHaveAttribute('href', '/visits/v1/works/w1');
  expect(screen.getByLabelText('Госномер А123ВС77')).toBeInTheDocument();
  expect(screen.getByText('Диагностика подвески')).toBeInTheDocument();
});

test('empty state', async () => {
  server.use(http.get('/api/work-items/mine', () => HttpResponse.json([])));
  renderApp('/my', { as: 'mechanic' });
  expect(await screen.findByText('Нет назначенных работ')).toBeInTheDocument();
});

test('done tab lists finished works with visit date and outcome, read-only', async () => {
  server.use(http.get('/api/work-items/mine/done', () => HttpResponse.json(doneList([
    makeDoneWork(),
    makeDoneWork({ id: 'd2', name: 'Развал-схождение', visit_status: 'cancelled', plate_number: null, make_model: null }),
  ]))));
  renderApp('/my/done', { as: 'mechanic' });
  expect(await screen.findByText('Замена масла ДВС')).toBeInTheDocument();
  expect(screen.getByLabelText('Госномер А123ВС77')).toBeInTheDocument();
  expect(screen.getAllByText('05.09.2026')).toHaveLength(2);
  expect(screen.getByText('✓ Выдан')).toBeInTheDocument();
  expect(screen.getByText('Отменён')).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: /Замена масла ДВС/ })).not.toBeInTheDocument();
});

test('done tab empty state', async () => {
  server.use(http.get('/api/work-items/mine/done', () => HttpResponse.json(doneList([]))));
  renderApp('/my/done', { as: 'mechanic' });
  expect(await screen.findByText('Выполненных работ пока нет')).toBeInTheDocument();
});

test('on the done tab only that tab is current', async () => {
  server.use(http.get('/api/work-items/mine/done', () => HttpResponse.json(doneList([]))));
  renderApp('/my/done', { as: 'mechanic' });
  const done = await screen.findByRole('link', { name: /Выполненные/ });
  expect(done).toHaveAttribute('aria-current', 'page');
  expect(screen.getByRole('link', { name: /Мои работы/ })).not.toHaveAttribute('aria-current');
});

function record(path: string, body: JsonBodyType) {
  const queries: URLSearchParams[] = [];
  server.use(http.get(path, ({ request }) => {
    queries.push(new URL(request.url).searchParams);
    return HttpResponse.json(body);
  }));
  return queries;
}
const lastOf = (queries: URLSearchParams[]) => queries[queries.length - 1];

test('my works: status chips and car grouping go to the server', async () => {
  const queries = record('/api/work-items/mine', [
    makeMyWork(), makeMyWork({ id: 'w2', name: 'Развал', status: 'ready' }),
    makeMyWork({ id: 'w3', visit_id: 'v2', name: 'Генератор', plate_number: 'В222ВВ77', make_model: 'Kia Rio' }),
  ]);
  const { user } = renderApp('/my', { as: 'mechanic' });
  await screen.findByRole('link', { name: /Генератор/ });
  expect(lastOf(queries).get('sort')).toBe('urgency');
  await user.selectOptions(screen.getByLabelText('Статус'), 'waiting_parts');
  await waitFor(() => expect(lastOf(queries).getAll('status')).toEqual(['waiting_parts']));
  await user.selectOptions(screen.getByLabelText('Порядок'), 'car');
  await waitFor(() => expect(lastOf(queries).get('sort')).toBe('car'));
  expect(await screen.findByRole('heading', { name: 'А123ВС77 · Toyota Camry' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'В222ВВ77 · Kia Rio' })).toBeInTheDocument();
});

test('my works: filtered empty state', async () => {
  record('/api/work-items/mine', []);
  const { user } = renderApp('/my', { as: 'mechanic' });
  await screen.findByText('Нет назначенных работ');
  await user.selectOptions(screen.getByLabelText('Статус'), 'ready');
  expect(await screen.findByText('Нет работ с этим фильтром')).toBeInTheDocument();
});

test('done: month by default with a norm-hours total, period and outcome go to the server', async () => {
  const queries = record('/api/work-items/mine/done', doneList(
    [makeDoneWork(), makeDoneWork({ id: 'd2', norm_hours: 1.5 })], { count: 2, total_norm_hours: 3 },
  ));
  const { user } = renderApp('/my/done', { as: 'mechanic' });
  expect(await screen.findByText('Работ: 2 · 3 н/ч')).toBeInTheDocument();
  const since = new Date(lastOf(queries).get('since')!).getTime();
  expect(Math.abs(Date.now() - 30 * 86_400_000 - since)).toBeLessThan(60_000);
  await user.selectOptions(screen.getByLabelText('Период'), 'all');
  await waitFor(() => expect(lastOf(queries).has('since')).toBe(false));
  await user.selectOptions(screen.getByLabelText('Итог'), 'cancelled');
  await waitFor(() => expect(lastOf(queries).get('outcome')).toBe('cancelled'));
});

test('mechanic can sign out from the header', async () => {
  server.use(
    http.get('/api/work-items/mine', () => HttpResponse.json([])),
    http.get('/api/auth/dev-users', () => HttpResponse.json([])),
  );
  const { user } = renderApp('/my', { as: 'mechanic' });
  const header = (await screen.findByRole('heading', { name: 'Мои работы' })).closest('header')!;
  expect(header).toHaveTextContent('Сидоров Иван');
  await user.click(within(header).getByRole('button', { name: 'Выйти' }));
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/login'));
});

test('done tab has the header sign-out too', async () => {
  server.use(http.get('/api/work-items/mine/done', () => HttpResponse.json(doneList([]))));
  renderApp('/my/done', { as: 'mechanic' });
  await screen.findByRole('heading', { name: 'Выполненные работы' });
  expect(screen.getByRole('button', { name: 'Выйти' })).toBeInTheDocument();
});
