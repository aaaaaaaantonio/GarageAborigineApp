import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { makeVisit, mockVisitPage } from '../test/fixtures';
import { renderApp } from '../test/render';
import { server } from '../test/server';

const visits = [
  makeVisit({ id: 'v1', plate_number: 'А123ВС77', status: 'in_progress', assigned_master_id: 'u-master' }),
  makeVisit({ id: 'v2', plate_number: 'Х777ХХ99', make_model: 'Kia Rio', status: 'waiting_parts', assigned_master_id: 'u-other', master_name: 'Другой' }),
];

test('lists active visits as cards', async () => {
  server.use(http.get('/api/visits', () => HttpResponse.json({ items: visits, has_more: false })));
  renderApp('/visits', { as: 'master' });
  expect(await screen.findByLabelText('Госномер А123ВС77')).toBeInTheDocument();
  expect(screen.getByLabelText('Госномер Х777ХХ99')).toBeInTheDocument();
  expect(screen.getByText('Ждём запчасти')).toBeInTheDocument();
});

test('filters by mine and waiting parts', async () => {
  server.use(http.get('/api/visits', () => HttpResponse.json({ items: visits, has_more: false })));
  const { user } = renderApp('/visits', { as: 'master' });
  await screen.findByLabelText('Госномер А123ВС77');
  await user.click(screen.getByRole('button', { name: 'Мои' }));
  expect(screen.getByLabelText('Госномер А123ВС77')).toBeInTheDocument();
  expect(screen.queryByLabelText('Госномер Х777ХХ99')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Ждут запчасти' }));
  expect(screen.getByLabelText('Госномер Х777ХХ99')).toBeInTheDocument();
  expect(screen.queryByLabelText('Госномер А123ВС77')).not.toBeInTheDocument();
});

test('empty list offers a new visit', async () => {
  server.use(http.get('/api/visits', () => HttpResponse.json({ items: [], has_more: false })));
  renderApp('/visits', { as: 'master' });
  const empty = await screen.findByText('Нет заездов в работе');
  expect(within(empty.parentElement!).getByRole('link', { name: '+ Новый заезд' })).toHaveAttribute('href', '/visits/new');
});

test('card opens the visit', async () => {
  server.use(http.get('/api/visits', () => HttpResponse.json({ items: visits, has_more: false })));
  mockVisitPage();
  const { user } = renderApp('/visits', { as: 'master' });
  await user.click(await screen.findByLabelText('Госномер А123ВС77'));
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/visits/v1'));
});
