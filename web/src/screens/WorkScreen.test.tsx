import { screen, waitFor, within } from '@testing-library/react';
import { delay, http, HttpResponse } from 'msw';
import { USERS, renderApp } from '../test/render';
import { makeMyWork, makeWorkItem } from '../test/fixtures';
import { server } from '../test/server';

function staffItem(over = {}) {
  server.use(http.get('/api/visits/v1/work-items', () => HttpResponse.json([makeWorkItem(over)])));
}

test('staff sees status steps, approve, part and reassign', async () => {
  staffItem();
  renderApp('/visits/v1/works/w1', { as: 'master' });
  expect(await screen.findByText('Замена масла ДВС')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Ждёт запчасти/ })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Готово/ })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Согласовано клиентом' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: '+ Запчасть' })).toHaveAttribute('href', '/visits/v1/works/w1/parts/new');
  expect(screen.getByRole('button', { name: 'Сменить исполнителя' })).toBeInTheDocument();
});

test('mechanic sees only status steps', async () => {
  server.use(http.get('/api/work-items/mine', () => HttpResponse.json([makeMyWork()])));
  renderApp('/visits/v1/works/w1', { as: 'mechanic' });
  expect(await screen.findByRole('button', { name: /В работе/ })).toBeInTheDocument();
  expect(screen.getByLabelText('Госномер А123ВС77')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Согласовано клиентом' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Сменить исполнителя' })).not.toBeInTheDocument();
});

test('status tap sends one PATCH even on double tap', async () => {
  staffItem();
  const calls: unknown[] = [];
  server.use(
    http.patch('/api/visits/v1/work-items/w1/status', async ({ request }) => {
      calls.push(await request.json());
      await delay(50);
      return HttpResponse.json(makeWorkItem({ status: 'ready', allowed_next_statuses: [] }));
    }),
  );
  const { user } = renderApp('/visits/v1/works/w1', { as: 'master' });
  const btn = await screen.findByRole('button', { name: /Готово/ });
  await user.dblClick(btn);
  await waitFor(() => expect(calls).toEqual([{ new_status: 'ready' }]));
});

test('reassign picks a mechanic or none', async () => {
  staffItem();
  const bodies: unknown[] = [];
  server.use(
    http.get('/api/users/mechanics', () => HttpResponse.json([USERS.mechanic, { ...USERS.mechanic, id: 'u-m2', full_name: 'Ахмедов Руслан' }])),
    http.patch('/api/visits/v1/work-items/w1/mechanic', async ({ request }) => {
      bodies.push(await request.json());
      return HttpResponse.json(makeWorkItem());
    }),
  );
  const { user } = renderApp('/visits/v1/works/w1', { as: 'master' });
  await user.click(await screen.findByRole('button', { name: 'Сменить исполнителя' }));
  const sheet = screen.getByRole('dialog', { name: 'Кому передать работу?' });
  await user.click(await within(sheet).findByRole('button', { name: 'Ахмедов Руслан' }));
  await waitFor(() => expect(bodies).toEqual([{ assigned_mechanic_id: 'u-m2' }]));
  await user.click(screen.getByRole('button', { name: 'Сменить исполнителя' }));
  await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Без исполнителя' }));
  await waitFor(() => expect(bodies[1]).toEqual({ assigned_mechanic_id: null }));
});

test('approve posts and hides the button', async () => {
  let approved = false;
  server.use(
    http.get('/api/visits/v1/work-items', () => HttpResponse.json([makeWorkItem({ approved_by_client: approved })])),
    http.post('/api/visits/v1/work-items/w1/approve', () => {
      approved = true;
      return HttpResponse.json(makeWorkItem({ approved_by_client: true }));
    }),
  );
  const { user } = renderApp('/visits/v1/works/w1', { as: 'master' });
  await user.click(await screen.findByRole('button', { name: 'Согласовано клиентом' }));
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Согласовано клиентом' })).not.toBeInTheDocument());
  expect(screen.getByText('✅ Согласовано клиентом')).toBeInTheDocument();
});

test('missing item shows not found', async () => {
  server.use(http.get('/api/work-items/mine', () => HttpResponse.json([])));
  renderApp('/visits/v1/works/zzz', { as: 'mechanic' });
  expect(await screen.findByText('Работа не найдена')).toBeInTheDocument();
});
