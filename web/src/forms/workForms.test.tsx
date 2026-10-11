import { screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { USERS, renderApp } from '../test/render';
import { makeWorkItem, mockVisitPage } from '../test/fixtures';
import { server } from '../test/server';

function mockCommon() {
  server.use(
    http.get('/api/users/mechanics', () => HttpResponse.json([USERS.mechanic])),
    http.get('/api/catalog/suggest', () =>
      HttpResponse.json([{ id: 'cat1', name: 'Замена масла ДВС', category: 'maintenance', default_norm_hours: 0.5 }])),
  );
}

test('picking from the catalog fills category and hours, posts and returns to the visit', async () => {
  mockCommon();
  mockVisitPage();
  let body: unknown;
  server.use(http.post('/api/visits/v1/work-items', async ({ request }) => {
    body = await request.json();
    return HttpResponse.json(makeWorkItem(), { status: 201 });
  }));
  const { user } = renderApp('/visits/v1/works/new', { as: 'master' });
  await user.type(await screen.findByLabelText('Название'), 'Замена');
  await user.click(await screen.findByRole('option', { name: /Замена масла ДВС/ }));
  expect(screen.queryByLabelText('Категория')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Нормо-часы')).toHaveValue('0.5');
  await user.type(screen.getByLabelText('Ставка, ₽/ч'), '2400');
  await user.selectOptions(screen.getByLabelText('Исполнитель'), 'u-mech');
  await user.click(screen.getByRole('button', { name: 'Добавить работу' }));
  await waitFor(() =>
    expect(body).toEqual({
      catalog_item_id: 'cat1', free_text_name: null, category: 'maintenance',
      norm_hours: 0.5, hourly_rate: 2400, assigned_mechanic_id: 'u-mech',
    }),
  );
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/visits/v1'));
});

test('free-text work needs a category and numbers; nothing is sent until valid', async () => {
  mockCommon();
  const post = vi.fn();
  server.use(http.post('/api/visits/v1/work-items', () => {
    post();
    return HttpResponse.json(makeWorkItem(), { status: 201 });
  }));
  const { user } = renderApp('/visits/v1/works/new', { as: 'master' });
  await user.type(await screen.findByLabelText('Название'), 'Своя работа');
  await user.type(screen.getByLabelText('Нормо-часы'), 'abc');
  await user.click(screen.getByRole('button', { name: 'Добавить работу' }));
  expect(screen.getByText('Выберите категорию')).toBeInTheDocument();
  expect(screen.getByText('Нормо-часы — число больше 0')).toBeInTheDocument();
  expect(post).not.toHaveBeenCalled();
});

test('API 422 lands on the field', async () => {
  mockCommon();
  server.use(http.post('/api/visits/v1/work-items', () =>
    HttpResponse.json({ detail: [{ loc: ['body', 'hourly_rate'], msg: 'Input should be greater than 0' }] }, { status: 422 })));
  const { user } = renderApp('/visits/v1/works/new', { as: 'master' });
  await user.type(await screen.findByLabelText('Название'), 'Своя работа');
  await user.selectOptions(screen.getByLabelText('Категория'), 'other');
  await user.type(screen.getByLabelText('Нормо-часы'), '1,5');
  await user.type(screen.getByLabelText('Ставка, ₽/ч'), '0');
  await user.click(screen.getByRole('button', { name: 'Добавить работу' }));
  expect(await screen.findByText('Input should be greater than 0')).toBeInTheDocument();
  expect(screen.getByLabelText('Название')).toHaveValue('Своя работа');
});

test('add part posts and returns to the work', async () => {
  let body: unknown;
  server.use(
    http.post('/api/visits/v1/part-items', async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: 'p1', name: 'Фильтр', quantity: 2, unit_price: 450.5 }, { status: 201 });
    }),
    http.get('/api/visits/v1/work-items', () => HttpResponse.json([makeWorkItem()])),
    http.get('/api/visits/v1/lines', () => HttpResponse.json({ works: [], works_total: 0, parts_total: 0, discount: 0, total: 0 })),
  );
  const { user } = renderApp('/visits/v1/works/w1/parts/new', { as: 'master' });
  await user.type(await screen.findByLabelText('Название'), 'Фильтр');
  await user.clear(screen.getByLabelText('Количество'));
  await user.type(screen.getByLabelText('Количество'), '2');
  await user.type(screen.getByLabelText('Цена за штуку, ₽'), '450,5');
  await user.click(screen.getByRole('button', { name: 'Добавить запчасть' }));
  await waitFor(() => expect(body).toEqual({ work_item_id: 'w1', name: 'Фильтр', quantity: 2, unit_price: 450.5 }));
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/visits/v1/works/w1'));
});
