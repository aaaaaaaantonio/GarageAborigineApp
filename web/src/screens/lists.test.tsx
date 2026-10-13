import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import type { BoardItem, Visit } from '../api/types';
import { makeVisit } from '../test/fixtures';
import { renderApp } from '../test/render';
import { server } from '../test/server';

const last = (queries: URLSearchParams[]) => queries[queries.length - 1];

// --- archive ---

function serveArchive(pages: Visit[][], totals = { total_count: 0, issued_amount: 0 }) {
  const queries: URLSearchParams[] = [];
  server.use(
    http.get('/api/visits', ({ request }) => {
      const params = new URL(request.url).searchParams;
      queries.push(params);
      const page = Number(params.get('offset') ?? 0) === 0 ? 0 : 1;
      return HttpResponse.json({ items: pages[page] ?? [], has_more: page < pages.length - 1, ...totals });
    }),
  );
  return queries;
}

const issued = makeVisit({ id: 'a1', status: 'issued', total_amount: 12500, status_changed_at: '2026-10-01T10:00:00Z' });
const cancelled = makeVisit({ id: 'a2', plate_number: 'Х777ХХ99', status: 'cancelled', total_amount: 0 });

test('archive asks for closed visits of the last month and shows totals', async () => {
  const queries = serveArchive([[issued, cancelled]], { total_count: 2, issued_amount: 12500 });
  renderApp('/visits/archive', { as: 'master' });
  expect(await screen.findByText('Заездов: 2 · Выручка: 12 500 ₽')).toBeInTheDocument();
  expect(screen.getByText('✓ Выдан')).toBeInTheDocument();
  expect(screen.getByText('Отменён')).toBeInTheDocument();
  expect(screen.getByText(/01\.10\.2026/)).toBeInTheDocument();
  const q = last(queries);
  expect(q.get('closed')).toBe('true');
  expect(q.get('sort')).toBe('date');
  const since = new Date(q.get('since')!).getTime();
  expect(Math.abs(Date.now() - 30 * 86_400_000 - since)).toBeLessThan(60_000);
});

test('archive filters by period, outcome and sort', async () => {
  const queries = serveArchive([[issued]]);
  const { user } = renderApp('/visits/archive', { as: 'master' });
  await screen.findByText('✓ Выдан');
  await user.selectOptions(screen.getByLabelText('Период'), 'all');
  await waitFor(() => expect(last(queries).has('since')).toBe(false));
  await user.selectOptions(screen.getByLabelText('Итог'), 'cancelled');
  await waitFor(() => expect(last(queries).getAll('status')).toEqual(['cancelled']));
  await user.selectOptions(screen.getByLabelText('Сортировка'), 'amount');
  await waitFor(() => expect(last(queries).get('sort')).toBe('amount'));
});

test('archive loads more pages', async () => {
  const queries = serveArchive([[issued], [cancelled]]);
  const { user } = renderApp('/visits/archive', { as: 'master' });
  await screen.findByText('✓ Выдан');
  await user.click(screen.getByRole('button', { name: 'Показать ещё' }));
  expect(await screen.findByText('Отменён')).toBeInTheDocument();
  expect(screen.getByText('✓ Выдан')).toBeInTheDocument();
  expect(last(queries).get('offset')).toBe('1');
  expect(screen.queryByRole('button', { name: 'Показать ещё' })).not.toBeInTheDocument();
});

test('archive empty state', async () => {
  serveArchive([[]]);
  renderApp('/visits/archive', { as: 'master' });
  expect(await screen.findByText('За этот период закрытых заездов нет')).toBeInTheDocument();
});

// --- board ---

function boardItem(over: Partial<BoardItem>): BoardItem {
  return {
    id: 'w1', visit_id: 'v1', name: 'Замена масла', status: 'in_progress', category: 'maintenance',
    approved_by_client: true, norm_hours: 1, assigned_mechanic_id: 'm1', assigned_mechanic_name: 'Морозов',
    plate_number: 'А123ВС77', make_model: 'Toyota Camry', visit_status: 'in_progress', ...over,
  };
}

function serveBoard(items: BoardItem[]) {
  const queries: URLSearchParams[] = [];
  server.use(
    http.get('/api/work-items/board', ({ request }) => {
      queries.push(new URL(request.url).searchParams);
      return HttpResponse.json({ items, has_more: false });
    }),
    http.get('/api/users/mechanics', () => HttpResponse.json([
      { id: 'm1', role: 'mechanic', full_name: 'Морозов', telegram_id: null, phone: null, branch_id: 'b1' },
    ])),
  );
  return queries;
}

const board = [
  boardItem({ id: 'w0', name: 'Без исполнителя работа', assigned_mechanic_id: null, assigned_mechanic_name: null, status: 'not_ready', approved_by_client: false }),
  boardItem({ id: 'w1' }),
  boardItem({ id: 'w2', name: 'Генератор', status: 'waiting_parts', plate_number: 'В222ВВ77' }),
];

test('board groups by mechanic with headers and links to works', async () => {
  const queries = serveBoard(board);
  renderApp('/works', { as: 'master' });
  const free = await screen.findByRole('heading', { name: 'Без исполнителя' });
  expect(screen.getByRole('heading', { name: 'Морозов' })).toBeInTheDocument();
  expect(free).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Генератор/ })).toHaveAttribute('href', '/visits/v1/works/w2');
  expect(screen.getByText('не согласовано')).toBeInTheDocument();
  expect(last(queries).get('group')).toBe('mechanic');
});

test('board filters go to the server', async () => {
  const queries = serveBoard(board);
  const { user } = renderApp('/works', { as: 'admin' });
  await screen.findByRole('heading', { name: 'Морозов' });
  await user.selectOptions(screen.getByLabelText('Механик'), 'none');
  await waitFor(() => expect(last(queries).get('unassigned')).toBe('true'));
  await user.selectOptions(screen.getByLabelText('Механик'), 'm1');
  await waitFor(() => expect(last(queries).get('mechanic_id')).toBe('m1'));
  await user.selectOptions(screen.getByLabelText('Статус работы'), 'waiting_parts');
  await waitFor(() => expect(last(queries).getAll('status')).toEqual(['waiting_parts']));
  await user.selectOptions(screen.getByLabelText('Категория'), 'electrical');
  await waitFor(() => expect(last(queries).getAll('category')).toEqual(['electrical']));
  await user.selectOptions(screen.getByLabelText('Согласование'), 'unapproved');
  await waitFor(() => expect(last(queries).get('unapproved')).toBe('true'));
  await user.selectOptions(screen.getByLabelText('Группировка'), 'car');
  await waitFor(() => expect(last(queries).get('group')).toBe('car'));
  expect(await screen.findByRole('heading', { name: 'В222ВВ77 · Toyota Camry' })).toBeInTheDocument();
});

test('board empty state and mechanic has no access', async () => {
  serveBoard([]);
  renderApp('/works', { as: 'master' });
  expect(await screen.findByText('Работ с этим фильтром нет')).toBeInTheDocument();
});

test('more screen links to board and archive', async () => {
  renderApp('/more', { as: 'master' });
  const more = await screen.findByRole('link', { name: 'Доска работ' });
  expect(more).toHaveAttribute('href', '/works');
  expect(within(more.parentElement!).getByRole('link', { name: 'Архив заездов' })).toHaveAttribute('href', '/visits/archive');
});

test('mechanic cannot open the board', async () => {
  renderApp('/works', { as: 'mechanic' });
  expect(await screen.findByText('Нет доступа к этому разделу')).toBeInTheDocument();
});
