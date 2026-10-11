import { screen, waitFor } from '@testing-library/react';
import { delay, http, HttpResponse } from 'msw';
import { CLIENT, VEHICLE, makeVisit, mockVisitPage } from '../test/fixtures';
import { USERS, renderApp } from '../test/render';
import { server } from '../test/server';

function mockClientSearch(hits = [{ entity: 'client', id: 'c1', matched_field: 'full_name' }]) {
  server.use(
    http.get('/api/search', () => HttpResponse.json(hits)),
    http.get('/api/clients/c1', () => HttpResponse.json(CLIENT)),
    http.get('/api/clients/c1/vehicles', () => HttpResponse.json([VEHICLE])),
  );
}

function captureCreate(bodies: unknown[], responses: Response[] = []) {
  server.use(http.post('/api/visits', async ({ request }) => {
    bodies.push(await request.json());
    return responses.shift() ?? HttpResponse.json(makeVisit(), { status: 201 });
  }));
}

test('master: client → vehicle → mileage → visit card', async () => {
  mockClientSearch();
  mockVisitPage();
  const bodies: unknown[] = [];
  captureCreate(bodies);
  const { user } = renderApp('/visits/new', { as: 'master' });
  await user.type(await screen.findByLabelText('Телефон или ФИО клиента'), 'Петров');
  await user.click(await screen.findByRole('button', { name: /Петров Иван/ }));
  await user.click(await screen.findByRole('button', { name: /Toyota Camry/ }));
  await user.type(await screen.findByLabelText('Пробег на приёмке, км'), '130000');
  await user.click(screen.getByRole('button', { name: 'Создать заезд' }));
  await waitFor(() =>
    expect(bodies).toEqual([{ client_id: 'c1', vehicle_id: 'veh1', assigned_master_id: 'u-master', mileage_at_intake: 130000, mileage_manually_confirmed: false }]),
  );
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/visits/v1'));
});

test('admin picks the master', async () => {
  mockClientSearch();
  mockVisitPage();
  server.use(http.get('/api/users/masters', () => HttpResponse.json([USERS.master])));
  const bodies: unknown[] = [];
  captureCreate(bodies);
  const { user } = renderApp('/visits/new', { as: 'admin' });
  await user.type(await screen.findByLabelText('Телефон или ФИО клиента'), 'Петров');
  await user.click(await screen.findByRole('button', { name: /Петров Иван/ }));
  await user.click(await screen.findByRole('button', { name: /Toyota Camry/ }));
  await user.type(await screen.findByLabelText('Пробег на приёмке, км'), '130000');
  await user.click(screen.getByRole('button', { name: 'Далее' }));
  await user.click(await screen.findByRole('button', { name: 'Орлов Пётр' }));
  await waitFor(() => expect(bodies[0]).toMatchObject({ assigned_master_id: 'u-master' }));
});

test('client not found → create client → create vehicle → mileage', async () => {
  server.use(
    http.get('/api/search', () => HttpResponse.json([])),
    http.post('/api/clients', () => HttpResponse.json(CLIENT, { status: 201 })),
    http.get('/api/clients/c1/vehicles', () => HttpResponse.json([])),
    http.post('/api/vehicles', () => HttpResponse.json(VEHICLE, { status: 201 })),
    http.post('/api/vehicles/veh1/owners', () => HttpResponse.json({ id: 'o1' }, { status: 201 })),
  );
  const { user } = renderApp('/visits/new', { as: 'master' });
  await user.type(await screen.findByLabelText('Телефон или ФИО клиента'), '+7 900 123-45-67');
  expect(await screen.findByText('Клиент не найден')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: '+ Новый клиент' }));
  expect(screen.getByLabelText('Телефон')).toHaveValue('+7 900 123-45-67');
  await user.type(screen.getByLabelText('ФИО'), 'Петров Иван');
  await user.click(screen.getByRole('button', { name: 'Создать и продолжить' }));
  await user.click(await screen.findByRole('button', { name: '+ Новый автомобиль' }));
  await user.type(screen.getByLabelText('VIN или номер кузова'), 'JTDBR32E720012345');
  await user.type(screen.getByLabelText('Госномер'), 'А123ВС77');
  await user.type(screen.getByLabelText('Марка'), 'Toyota');
  await user.type(screen.getByLabelText('Модель'), 'Camry');
  await user.click(screen.getByRole('button', { name: 'Создать и продолжить' }));
  expect(await screen.findByLabelText('Пробег на приёмке, км')).toBeInTheDocument();
});

test('mileage rollback asks to confirm and resends with the flag', async () => {
  mockClientSearch();
  mockVisitPage();
  const bodies: unknown[] = [];
  captureCreate(bodies, [
    HttpResponse.json({ detail: 'Пробег меньше последнего зафиксированного, требуется mileage_manually_confirmed=true' }, { status: 409 }),
  ]);
  const { user } = renderApp('/visits/new', { as: 'master' });
  await user.type(await screen.findByLabelText('Телефон или ФИО клиента'), 'Петров');
  await user.click(await screen.findByRole('button', { name: /Петров Иван/ }));
  await user.click(await screen.findByRole('button', { name: /Toyota Camry/ }));
  await user.type(await screen.findByLabelText('Пробег на приёмке, км'), '1000');
  await user.click(screen.getByRole('button', { name: 'Создать заезд' }));
  await user.click(await screen.findByRole('button', { name: 'Подтвердить пробег' }));
  await waitFor(() => expect(bodies).toHaveLength(2));
  expect(bodies[1]).toMatchObject({ mileage_at_intake: 1000, mileage_manually_confirmed: true });
});

test('back keeps typed values', async () => {
  mockClientSearch();
  const { user } = renderApp('/visits/new', { as: 'master' });
  await user.type(await screen.findByLabelText('Телефон или ФИО клиента'), 'Петров');
  await user.click(await screen.findByRole('button', { name: /Петров Иван/ }));
  await user.click(await screen.findByRole('button', { name: /Toyota Camry/ }));
  await user.type(await screen.findByLabelText('Пробег на приёмке, км'), '5');
  await user.click(screen.getByRole('button', { name: 'Назад' }));
  await user.click(await screen.findByRole('button', { name: /Toyota Camry/ }));
  expect(await screen.findByLabelText('Пробег на приёмке, км')).toHaveValue('5');
  await user.click(screen.getByRole('button', { name: 'Назад' }));
  await user.click(screen.getByRole('button', { name: 'Назад' }));
  expect(screen.getByLabelText('Телефон или ФИО клиента')).toHaveValue('Петров');
});

test('wizard is full screen; Отмена asks before dropping the draft', async () => {
  mockClientSearch();
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  const { user } = renderApp('/visits/new', { as: 'master' });
  await user.type(await screen.findByLabelText('Телефон или ФИО клиента'), 'Петров');
  expect(screen.queryByRole('navigation', { name: 'Разделы' })).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Отмена' }));
  expect(confirm).toHaveBeenCalledWith('Прервать новый заезд?');
  expect(screen.getByTestId('location')).toHaveTextContent(/^\/visits\/new$/);
  confirm.mockReturnValue(true);
  await user.click(screen.getByRole('button', { name: 'Отмена' }));
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(/^\/visits$/));
  confirm.mockRestore();
});

test('Отмена on an untouched wizard leaves without asking', async () => {
  const confirm = vi.spyOn(window, 'confirm');
  const { user } = renderApp('/visits/new', { as: 'master' });
  await user.click(await screen.findByRole('button', { name: 'Отмена' }));
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(/^\/visits$/));
  expect(confirm).not.toHaveBeenCalled();
  confirm.mockRestore();
});

test('vehicle_id preset starts at mileage', async () => {
  server.use(
    http.get('/api/vehicles/veh1', () => HttpResponse.json(VEHICLE)),
    http.get('/api/vehicles/veh1/owner', () => HttpResponse.json(CLIENT)),
  );
  renderApp('/visits/new?vehicle_id=veh1', { as: 'master' });
  expect(await screen.findByLabelText('Пробег на приёмке, км')).toBeInTheDocument();
  expect(screen.getByText(/Петров Иван/)).toBeInTheDocument();
  expect(screen.getByText('Последний пробег: 120 500 км')).toBeInTheDocument();
});

test('create visit submits once on double tap', async () => {
  mockClientSearch();
  mockVisitPage();
  const bodies: unknown[] = [];
  server.use(http.post('/api/visits', async ({ request }) => {
    bodies.push(await request.json());
    await delay(50);
    return HttpResponse.json(makeVisit(), { status: 201 });
  }));
  const { user } = renderApp('/visits/new', { as: 'master' });
  await user.type(await screen.findByLabelText('Телефон или ФИО клиента'), 'Петров');
  await user.click(await screen.findByRole('button', { name: /Петров Иван/ }));
  await user.click(await screen.findByRole('button', { name: /Toyota Camry/ }));
  await user.type(await screen.findByLabelText('Пробег на приёмке, км'), '130000');
  await user.dblClick(screen.getByRole('button', { name: 'Создать заезд' }));
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/visits/v1'));
  expect(bodies).toHaveLength(1);
});

const VEHICLE2 = { id: 'veh2', vin: 'WAUZZZ8K9BA123456', plate_number: 'К777КК77', make: 'Audi', model: 'A4', mileage_current: 50000 };

function mockVehicleSearch(hits: unknown[]) {
  server.use(
    http.get('/api/search', ({ request }) => {
      const q = new URL(request.url).searchParams.get('q');
      return HttpResponse.json(q === 'Петров' ? [{ entity: 'client', id: 'c1', matched_field: 'full_name' }] : hits);
    }),
    http.get('/api/clients/c1', () => HttpResponse.json(CLIENT)),
    http.get('/api/clients/c1/vehicles', () => HttpResponse.json([VEHICLE])),
    http.get('/api/vehicles/veh2', () => HttpResponse.json(VEHICLE2)),
  );
}

async function toVehicleStep(user: ReturnType<typeof renderApp>['user']) {
  await user.type(await screen.findByLabelText('Телефон или ФИО клиента'), 'Петров');
  await user.click(await screen.findByRole('button', { name: /Петров Иван/ }));
}

test('vehicle step: search by plate picks another car for the chosen client', async () => {
  mockVehicleSearch([{ entity: 'vehicle', id: 'veh2', matched_field: 'plate_number' }]);
  mockVisitPage();
  const bodies: unknown[] = [];
  captureCreate(bodies);
  const { user } = renderApp('/visits/new', { as: 'master' });
  await toVehicleStep(user);
  await user.type(await screen.findByLabelText('Госномер или VIN'), 'К777');
  await user.click(await screen.findByRole('button', { name: /Audi A4/ }));
  await user.type(await screen.findByLabelText('Пробег на приёмке, км'), '60000');
  await user.click(screen.getByRole('button', { name: 'Создать заезд' }));
  await waitFor(() => expect(bodies).toEqual([expect.objectContaining({ client_id: 'c1', vehicle_id: 'veh2', mileage_at_intake: 60000 })]));
});

test('vehicle step: not found offers a new car prefilled with the query', async () => {
  mockVehicleSearch([]);
  const { user } = renderApp('/visits/new', { as: 'master' });
  await toVehicleStep(user);
  await user.type(await screen.findByLabelText('Госномер или VIN'), 'О555ОО77');
  expect(await screen.findByText('Автомобиль не найден')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: '+ Новый автомобиль' }));
  expect(screen.getByLabelText('Госномер')).toHaveValue('О555ОО77');
});

test('picking a different car clears the previous mileage', async () => {
  mockVehicleSearch([{ entity: 'vehicle', id: 'veh2', matched_field: 'plate_number' }]);
  const { user } = renderApp('/visits/new', { as: 'master' });
  await toVehicleStep(user);
  await user.click(await screen.findByRole('button', { name: /Toyota Camry/ }));
  await user.type(await screen.findByLabelText('Пробег на приёмке, км'), '130000');
  await user.click(screen.getByRole('button', { name: 'Назад' }));
  await user.type(await screen.findByLabelText('Госномер или VIN'), 'К777');
  await user.click(await screen.findByRole('button', { name: /Audi A4/ }));
  expect(await screen.findByLabelText('Пробег на приёмке, км')).toHaveValue('');
});

test('back after creating a client and a car never returns to the creation forms', async () => {
  server.use(
    http.get('/api/search', () => HttpResponse.json([])),
    http.post('/api/clients', () => HttpResponse.json(CLIENT, { status: 201 })),
    http.get('/api/clients/c1/vehicles', () => HttpResponse.json([])),
    http.post('/api/vehicles', () => HttpResponse.json(VEHICLE, { status: 201 })),
    http.post('/api/vehicles/veh1/owners', () => HttpResponse.json({ id: 'o1' }, { status: 201 })),
  );
  const { user } = renderApp('/visits/new', { as: 'master' });
  await user.type(await screen.findByLabelText('Телефон или ФИО клиента'), '+7 900 123-45-67');
  await user.click(await screen.findByRole('button', { name: '+ Новый клиент' }));
  await user.type(screen.getByLabelText('ФИО'), 'Петров Иван');
  await user.click(screen.getByRole('button', { name: 'Создать и продолжить' }));
  await user.click(await screen.findByRole('button', { name: '+ Новый автомобиль' }));
  await user.type(screen.getByLabelText('VIN или номер кузова'), 'JTDBR32E720012345');
  await user.type(screen.getByLabelText('Госномер'), 'А123ВС77');
  await user.type(screen.getByLabelText('Марка'), 'Toyota');
  await user.type(screen.getByLabelText('Модель'), 'Camry');
  await user.click(screen.getByRole('button', { name: 'Создать и продолжить' }));
  await screen.findByLabelText('Пробег на приёмке, км');
  await user.click(screen.getByRole('button', { name: 'Назад' }));
  expect(await screen.findByLabelText('Госномер или VIN')).toBeInTheDocument();
  expect(screen.queryByLabelText('VIN или номер кузова')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Назад' }));
  expect(screen.getByLabelText('Телефон или ФИО клиента')).toBeInTheDocument();
  expect(screen.queryByLabelText('ФИО')).not.toBeInTheDocument();
});

test('editing the mileage after a rollback warning re-checks it instead of auto-confirming', async () => {
  mockClientSearch();
  const bodies: unknown[] = [];
  captureCreate(bodies, [HttpResponse.json({ detail: 'Пробег меньше' }, { status: 409 })]);
  const { user } = renderApp('/visits/new', { as: 'master' });
  await toVehicleStep(user);
  await user.click(await screen.findByRole('button', { name: /Toyota Camry/ }));
  await user.type(await screen.findByLabelText('Пробег на приёмке, км'), '1000');
  await user.click(screen.getByRole('button', { name: 'Создать заезд' }));
  await screen.findByRole('button', { name: 'Подтвердить пробег' });
  await user.type(screen.getByLabelText('Пробег на приёмке, км'), '5');
  expect(screen.queryByRole('button', { name: 'Подтвердить пробег' })).not.toBeInTheDocument();
});

test('mileage above 9 999 999 is rejected with a field error', async () => {
  mockClientSearch();
  const bodies: unknown[] = [];
  captureCreate(bodies);
  const { user } = renderApp('/visits/new', { as: 'master' });
  await toVehicleStep(user);
  await user.click(await screen.findByRole('button', { name: /Toyota Camry/ }));
  await user.type(await screen.findByLabelText('Пробег на приёмке, км'), '10000000');
  await user.click(screen.getByRole('button', { name: 'Создать заезд' }));
  expect(await screen.findByText('Пробег не больше 9 999 999 км')).toBeInTheDocument();
  expect(bodies).toHaveLength(0);
});
