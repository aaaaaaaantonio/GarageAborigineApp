import { screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { makeMyWork } from '../test/fixtures';
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
