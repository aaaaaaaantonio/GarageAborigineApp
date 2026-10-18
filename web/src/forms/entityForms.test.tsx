import { screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { CLIENT, VEHICLE } from '../test/fixtures';
import { USERS, renderApp } from '../test/render';
import { server } from '../test/server';

function mockClientPage() {
  server.use(
    http.get('/api/clients/c1', () => HttpResponse.json(CLIENT)),
    http.get('/api/clients/c1/vehicles', () => HttpResponse.json([])),
    http.get('/api/visits', () => HttpResponse.json({ items: [], has_more: false })),
  );
}

test('new client: bad phone blocked locally, 409 shown at phone', async () => {
  const post = vi.fn();
  server.use(http.post('/api/clients', () => {
    post();
    return HttpResponse.json({ detail: 'Клиент с таким телефоном уже есть' }, { status: 409 });
  }));
  const { user } = renderApp('/clients/new', { as: 'master' });
  await user.type(await screen.findByLabelText('Телефон'), '123');
  await user.type(screen.getByLabelText('ФИО'), 'Петров Иван');
  await user.click(screen.getByRole('button', { name: 'Создать клиента' }));
  expect(screen.getByText('Неверный формат телефона. Пример: +7 900 123-45-67')).toBeInTheDocument();
  expect(post).not.toHaveBeenCalled();
  await user.clear(screen.getByLabelText('Телефон'));
  await user.type(screen.getByLabelText('Телефон'), '+7 900 123-45-67');
  await user.click(screen.getByRole('button', { name: 'Создать клиента' }));
  expect(await screen.findByText('Клиент с таким телефоном уже есть')).toBeInTheDocument();
});

test('new client success opens the client card', async () => {
  mockClientPage();
  server.use(http.post('/api/clients', () => HttpResponse.json(CLIENT, { status: 201 })));
  const { user } = renderApp('/clients/new', { as: 'master' });
  await user.type(await screen.findByLabelText('Телефон'), '89001234567');
  await user.type(screen.getByLabelText('ФИО'), 'Петров Иван');
  await user.click(screen.getByRole('button', { name: 'Создать клиента' }));
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/clients/c1'));
});

test('new vehicle for a client normalizes input and attaches the owner', async () => {
  let created: unknown;
  let owner: unknown;
  server.use(
    http.post('/api/vehicles', async ({ request }) => {
      created = await request.json();
      return HttpResponse.json(VEHICLE, { status: 201 });
    }),
    http.post('/api/vehicles/veh1/owners', async ({ request }) => {
      owner = await request.json();
      return HttpResponse.json({ id: 'o1' }, { status: 201 });
    }),
    http.get('/api/vehicles/veh1', () => HttpResponse.json(VEHICLE)),
    http.get('/api/vehicles/veh1/owner', () => HttpResponse.json(CLIENT)),
    http.get('/api/vehicles/veh1/work-history', () => HttpResponse.json({ items: [], has_more: false })),
    http.get('/api/visits', () => HttpResponse.json({ items: [], has_more: false })),
  );
  const { user } = renderApp('/vehicles/new?client_id=c1', { as: 'master' });
  await user.type(await screen.findByLabelText('VIN или номер кузова'), 'jtdbr32e 720012345');
  await user.type(screen.getByLabelText('Госномер'), 'a123bc77');
  await user.type(screen.getByLabelText('Марка'), 'Toyota');
  await user.type(screen.getByLabelText('Модель'), 'Camry');
  await user.click(screen.getByRole('button', { name: 'Добавить автомобиль' }));
  await waitFor(() => expect(created).toEqual({ vin: 'JTDBR32E720012345', plate_number: 'А123ВС77', make: 'Toyota', model: 'Camry' }));
  await waitFor(() => expect(owner).toMatchObject({ client_id: 'c1' }));
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/vehicles/veh1'));
});

test('duplicate VIN shows at the VIN field', async () => {
  server.use(http.post('/api/vehicles', () => HttpResponse.json({ detail: 'Машина с таким VIN уже есть' }, { status: 409 })));
  const { user } = renderApp('/vehicles/new', { as: 'master' });
  await user.type(await screen.findByLabelText('VIN или номер кузова'), 'JTDBR32E720012345');
  await user.type(screen.getByLabelText('Госномер'), 'А123ВС77');
  await user.type(screen.getByLabelText('Марка'), 'Toyota');
  await user.type(screen.getByLabelText('Модель'), 'Camry');
  await user.click(screen.getByRole('button', { name: 'Добавить автомобиль' }));
  expect(await screen.findByText('Машина с таким VIN уже есть')).toBeInTheDocument();
});

test('paper consent registers and opens the client', async () => {
  mockClientPage();
  server.use(http.post('/api/consent/paper', () => HttpResponse.json({ client_id: 'c1' })));
  const { user } = renderApp('/consent/paper', { as: 'master' });
  await user.type(await screen.findByLabelText('Телефон'), '+79001234567');
  await user.type(screen.getByLabelText('ФИО'), 'Петров Иван');
  await user.click(screen.getByRole('button', { name: 'Зарегистрировать' }));
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/clients/c1'));
});

test('admin adds staff', async () => {
  let body: unknown;
  server.use(http.post('/api/users', async ({ request }) => {
    body = await request.json();
    return HttpResponse.json({ ...USERS.mechanic, id: 'u-new' }, { status: 201 });
  }));
  const { user } = renderApp('/staff/new', { as: 'admin' });
  await user.selectOptions(await screen.findByLabelText('Роль'), 'mechanic');
  await user.type(screen.getByLabelText('ФИО'), 'Ким Алексей');
  await user.type(screen.getByLabelText('Telegram ID'), '123456789');
  await user.click(screen.getByRole('button', { name: 'Добавить сотрудника' }));
  await waitFor(() => expect(body).toEqual({ role: 'mechanic', full_name: 'Ким Алексей', telegram_id: 123456789 }));
  expect(await screen.findByText('Сотрудник добавлен')).toBeInTheDocument();
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/more'));
});

test('more: staff link only for admin; sign out (in the header) returns to login', async () => {
  server.use(http.get('/api/auth/dev-users', () => HttpResponse.json([])));
  const { user } = renderApp('/more', { as: 'master' });
  expect(await screen.findByRole('link', { name: 'Бумажное согласие' })).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Добавить сотрудника' })).not.toBeInTheDocument();
  // One sign-out only: the header's.
  await user.click(screen.getByRole('button', { name: 'Выйти' }));
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/login'));
});

test('retry after owner attach failure does not re-create the vehicle', async () => {
  const posts = vi.fn();
  let attaches = 0;
  server.use(
    http.post('/api/vehicles', () => {
      posts();
      return HttpResponse.json(VEHICLE, { status: 201 });
    }),
    http.post('/api/vehicles/veh1/owners', () => {
      attaches += 1;
      return attaches === 1
        ? HttpResponse.json({ detail: 'Не удалось привязать владельца' }, { status: 500 })
        : HttpResponse.json({ id: 'o1' }, { status: 201 });
    }),
    http.get('/api/vehicles/veh1', () => HttpResponse.json(VEHICLE)),
    http.get('/api/vehicles/veh1/owner', () => HttpResponse.json(CLIENT)),
    http.get('/api/vehicles/veh1/work-history', () => HttpResponse.json({ items: [], has_more: false })),
    http.get('/api/visits', () => HttpResponse.json({ items: [], has_more: false })),
  );
  const { user } = renderApp('/vehicles/new?client_id=c1', { as: 'master' });
  await user.type(await screen.findByLabelText('VIN или номер кузова'), 'JTDBR32E720012345');
  await user.type(screen.getByLabelText('Госномер'), 'А123ВС77');
  await user.type(screen.getByLabelText('Марка'), 'Toyota');
  await user.type(screen.getByLabelText('Модель'), 'Camry');
  await user.click(screen.getByRole('button', { name: 'Добавить автомобиль' }));
  expect(await screen.findByRole('alert')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Добавить автомобиль' }));
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/vehicles/veh1'));
  expect(posts).toHaveBeenCalledTimes(1);
  expect(attaches).toBe(2);
});


test('more: admin gets his own work lists, master does not', async () => {
  const { unmount } = renderApp('/more', { as: 'admin' });
  expect(await screen.findByRole('link', { name: 'Мои работы' })).toHaveAttribute('href', '/my');
  expect(screen.queryByRole('link', { name: 'Мои выполненные' })).not.toBeInTheDocument();
  unmount();
  renderApp('/more', { as: 'master' });
  await screen.findByRole('link', { name: 'Бумажное согласие' });
  expect(screen.queryByRole('link', { name: 'Мои работы' })).not.toBeInTheDocument();
});
