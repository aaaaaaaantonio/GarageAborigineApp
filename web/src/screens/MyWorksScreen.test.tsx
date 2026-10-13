import { screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { makeDoneWork, makeMyWork } from '../test/fixtures';
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
  server.use(http.get('/api/work-items/mine/done', () => HttpResponse.json([
    makeDoneWork(),
    makeDoneWork({ id: 'd2', name: 'Развал-схождение', visit_status: 'cancelled', plate_number: null, make_model: null }),
  ])));
  renderApp('/my/done', { as: 'mechanic' });
  expect(await screen.findByText('Замена масла ДВС')).toBeInTheDocument();
  expect(screen.getByLabelText('Госномер А123ВС77')).toBeInTheDocument();
  expect(screen.getAllByText('05.09.2026')).toHaveLength(2);
  expect(screen.getByText('✓ Выдан')).toBeInTheDocument();
  expect(screen.getByText('Отменён')).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: /Замена масла ДВС/ })).not.toBeInTheDocument();
});

test('done tab empty state', async () => {
  server.use(http.get('/api/work-items/mine/done', () => HttpResponse.json([])));
  renderApp('/my/done', { as: 'mechanic' });
  expect(await screen.findByText('Выполненных работ пока нет')).toBeInTheDocument();
});

test('on the done tab only that tab is current', async () => {
  server.use(http.get('/api/work-items/mine/done', () => HttpResponse.json([])));
  renderApp('/my/done', { as: 'mechanic' });
  const done = await screen.findByRole('link', { name: /Выполненные/ });
  expect(done).toHaveAttribute('aria-current', 'page');
  expect(screen.getByRole('link', { name: /Мои работы/ })).not.toHaveAttribute('aria-current');
});
