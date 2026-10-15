import { screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { renderApp } from '../test/render';
import { makeMechanicVisit, pricedMechanicVisit } from '../test/fixtures';
import { server } from '../test/server';
import type { MechanicVisit } from '../api/types';

function serve(body: MechanicVisit) {
  server.use(http.get('/api/visits/v1/mechanic-view', () => HttpResponse.json(body)));
}

test('without prices: works and assignees, no money, no client', async () => {
  serve(makeMechanicVisit());
  renderApp('/my/visit/v1', { as: 'mechanic' });
  expect(await screen.findByText('Замена масла ДВС · моя')).toBeInTheDocument();
  expect(screen.getByText(/Морозов/)).toBeInTheDocument();
  expect(screen.getByText(/без исполнителя/)).toBeInTheDocument();
  expect(screen.getByText(/Мастер: Орлов Пётр/)).toBeInTheDocument();
  expect(screen.queryByText(/₽/)).not.toBeInTheDocument();
  expect(screen.queryByText(/Клиент:/)).not.toBeInTheDocument();
});

test('with prices and client data', async () => {
  serve(pricedMechanicVisit({ client_name: 'Петров Иван', client_phone: '+7 900 123-45-67', vin: 'XW8ZZZ61ZJG000001' }));
  renderApp('/my/visit/v1', { as: 'mechanic' });
  expect(await screen.findByText('Итого по заезду')).toBeInTheDocument();
  expect(screen.getByText('3 450 ₽')).toBeInTheDocument();
  expect(screen.getByText('Клиент: Петров Иван')).toBeInTheDocument();
  expect(screen.getByText('Телефон: +7 900 123-45-67')).toBeInTheDocument();
  expect(screen.getByText('VIN: XW8ZZZ61ZJG000001')).toBeInTheDocument();
  expect(screen.getByText('Ваш заработок по заезду').nextSibling).toHaveTextContent('1 000 ₽');
});

test('prices on but no pay scheme', async () => {
  serve(pricedMechanicVisit({ my_pay_total: null, works: [{ ...pricedMechanicVisit().works[0], my_pay: null }] }));
  renderApp('/my/visit/v1', { as: 'mechanic' });
  expect(await screen.findByText('Итого по заезду')).toBeInTheDocument();
  expect(screen.getAllByText('схема оплаты не задана')).toHaveLength(2);
});

test('done works open the visit card for a mechanic', async () => {
  server.use(http.get('/api/work-items/mine/done', () => HttpResponse.json({
    items: [{ id: 'w1', visit_id: 'v1', name: 'Замена масла ДВС', plate_number: 'А123ВС77', make_model: 'Toyota Camry',
      visit_status: 'issued', visit_date: '2026-10-10T09:00:00+00:00', closed_at: '2026-10-11T09:00:00+00:00', norm_hours: 2 }],
    count: 1, total_norm_hours: 2, has_more: false,
  })));
  renderApp('/my/done', { as: 'mechanic' });
  expect((await screen.findByText('Замена масла ДВС')).closest('a')).toHaveAttribute('href', '/my/visit/v1');
});
