import { screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { CLIENT, VEHICLE, makeVisit } from '../test/fixtures';
import { renderApp } from '../test/render';
import { server } from '../test/server';

function mockEntities() {
  server.use(
    http.get('/api/clients/c1', () => HttpResponse.json(CLIENT)),
    http.get('/api/vehicles/veh1', () => HttpResponse.json(VEHICLE)),
  );
}

test('search waits for input, then shows client and vehicle hits', async () => {
  mockEntities();
  const queries: string[] = [];
  server.use(
    http.get('/api/search/recent', () => HttpResponse.json([])),
    http.get('/api/search', ({ request }) => {
      queries.push(new URL(request.url).searchParams.get('q')!);
      return HttpResponse.json([
        { entity: 'client', id: 'c1', matched_field: 'full_name' },
        { entity: 'vehicle', id: 'veh1', matched_field: 'plate_number' },
      ]);
    }),
  );
  const { user } = renderApp('/search', { as: 'master' });
  expect(await screen.findByText('Введите госномер, VIN, телефон или ФИО')).toBeInTheDocument();
  await user.type(screen.getByRole('searchbox', { name: 'Поиск' }), 'Петров');
  expect(await screen.findByRole('link', { name: /Петров Иван/ })).toHaveAttribute('href', '/clients/c1');
  expect(screen.getByRole('link', { name: /Toyota Camry/ })).toHaveAttribute('href', '/vehicles/veh1');
  expect(queries).toEqual(['Петров']);
  expect(screen.getByTestId('location')).toHaveTextContent('/search?q=');
});

test('search with no results says so', async () => {
  server.use(
    http.get('/api/search/recent', () => HttpResponse.json([])),
    http.get('/api/search', () => HttpResponse.json([])),
  );
  const { user } = renderApp('/search', { as: 'master' });
  await user.type(await screen.findByRole('searchbox', { name: 'Поиск' }), 'zzzz');
  expect(await screen.findByText('Ничего не найдено')).toBeInTheDocument();
});

const VISIBILITY = {
  mechanic_sees_prices: false,
  mechanic_sees_client_name: true,
  mechanic_sees_client_phone: true,
  mechanic_sees_vin: true,
};

test('mechanic gets the vehicle-only hint', async () => {
  server.use(
    http.get('/api/search/recent', () => HttpResponse.json([{ entity_type: 'client', entity_id: 'c1' }])),
    http.get('/api/settings', () => HttpResponse.json(VISIBILITY)),
  );
  renderApp('/search', { as: 'mechanic' });
  expect(await screen.findByText('Введите госномер или VIN')).toBeInTheDocument();
});

test('mechanic hint drops VIN when the admin hides it', async () => {
  server.use(
    http.get('/api/search/recent', () => HttpResponse.json([])),
    http.get('/api/settings', () => HttpResponse.json({ ...VISIBILITY, mechanic_sees_vin: false })),
  );
  renderApp('/search', { as: 'mechanic' });
  expect(await screen.findByText('Введите госномер')).toBeInTheDocument();
  expect(screen.getByRole('searchbox', { name: 'Поиск' })).toHaveAttribute('placeholder', 'Госномер');
});

test('client card shows vehicles and visits', async () => {
  mockEntities();
  server.use(
    http.get('/api/clients/c1/vehicles', () => HttpResponse.json([VEHICLE])),
    http.get('/api/visits', ({ request }) => {
      expect(new URL(request.url).searchParams.get('client_id')).toBe('c1');
      return HttpResponse.json({ items: [makeVisit({ status: 'issued' })], has_more: false });
    }),
  );
  renderApp('/clients/c1', { as: 'master' });
  expect(await screen.findByText('Петров Иван')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: '+7 900 123-45-67' })).toHaveAttribute('href', 'tel:+79001234567');
  const links = await screen.findAllByRole('link', { name: /Toyota Camry/ });
  expect(links.map((l) => l.getAttribute('href'))).toContain('/vehicles/veh1');
  expect(await screen.findByText('✓ Выдан')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: '+ Автомобиль' })).toHaveAttribute('href', '/vehicles/new?client_id=c1');
});

test('vehicle card for staff shows owner, visits, history and new visit', async () => {
  mockEntities();
  server.use(
    http.get('/api/vehicles/veh1/owner', () => HttpResponse.json(CLIENT)),
    http.get('/api/vehicles/veh1/work-history', () =>
      HttpResponse.json({ items: [{ visit_id: 'v1', visit_at: '2026-09-01T10:00:00Z', mileage: 110000, name: 'Замена масла ДВС', status: 'ready', category: 'maintenance' }], has_more: false })),
    http.get('/api/visits', () => HttpResponse.json({ items: [makeVisit()], has_more: false })),
  );
  renderApp('/vehicles/veh1', { as: 'master' });
  expect(await screen.findByRole('link', { name: /Петров Иван/ })).toHaveAttribute('href', '/clients/c1');
  expect(screen.getByRole('link', { name: '+ Новый заезд' })).toHaveAttribute('href', '/visits/new?vehicle_id=veh1');
  expect(await screen.findByText('Замена масла ДВС')).toBeInTheDocument();
  expect(screen.getByText('01.09.2026 · 110 000 км')).toBeInTheDocument();
});

test('vehicle card for mechanic asks for neither owner nor visits', async () => {
  mockEntities();
  const visitsCalled = vi.fn();
  server.use(
    http.get('/api/vehicles/veh1/work-history', () => HttpResponse.json({ items: [], has_more: false })),
    http.get('/api/visits', () => {
      visitsCalled();
      return HttpResponse.json({ items: [], has_more: false });
    }),
  );
  renderApp('/vehicles/veh1', { as: 'mechanic' });
  expect(await screen.findByText('Работ по машине ещё не было')).toBeInTheDocument();
  expect(screen.queryByText('Владелец')).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: '+ Новый заезд' })).not.toBeInTheDocument();
  await waitFor(() => expect(screen.getByText('Toyota Camry')).toBeInTheDocument());
  expect(visitsCalled).not.toHaveBeenCalled();
});

test('vehicle history filters by category on the server', async () => {
  mockEntities();
  const queries: URLSearchParams[] = [];
  server.use(
    http.get('/api/vehicles/veh1/owner', () => HttpResponse.json(CLIENT)),
    http.get('/api/vehicles/veh1/work-history', ({ request }) => {
      queries.push(new URL(request.url).searchParams);
      return HttpResponse.json({ items: [], has_more: false });
    }),
    http.get('/api/visits', () => HttpResponse.json({ items: [], has_more: false })),
  );
  const { user } = renderApp('/vehicles/veh1', { as: 'mechanic' });
  await screen.findByText('Работ по машине ещё не было');
  await user.selectOptions(screen.getByLabelText('Категория'), 'chassis');
  await waitFor(() => expect(queries[queries.length - 1].getAll('category')).toEqual(['chassis']));
  expect(await screen.findByText('Работ этой категории не было')).toBeInTheDocument();
});

test('vehicle card skips the VIN when the server hides it', async () => {
  server.use(
    http.get('/api/vehicles/veh1', () => HttpResponse.json({ ...VEHICLE, vin: null })),
    http.get('/api/vehicles/veh1/work-history', () => HttpResponse.json({ items: [], has_more: false })),
  );
  renderApp('/vehicles/veh1', { as: 'mechanic' });
  expect(await screen.findByText('Toyota Camry')).toBeInTheDocument();
  expect(screen.queryByText(/VIN/)).not.toBeInTheDocument();
  expect(screen.queryByText(/null/)).not.toBeInTheDocument();
});
