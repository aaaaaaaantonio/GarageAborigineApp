import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { telegram } from '../telegram/webapp';
import { makeVisit, makeWorkLine, mockVisitPage } from '../test/fixtures';
import { renderApp } from '../test/render';
import { server } from '../test/server';

test('shows header, total, priced works and their parts', async () => {
  mockVisitPage(makeVisit(), [
    makeWorkLine(),
    makeWorkLine({ id: 'w2', name: 'Колодки передние', status: 'ready', assigned_mechanic_name: null, approved_by_client: true, amount: 2400, parts: [] }),
  ]);
  renderApp('/visits/v1', { as: 'master' });
  expect(await screen.findByLabelText('Госномер А123ВС77')).toBeInTheDocument();
  expect(screen.getByText('Toyota Camry')).toBeInTheDocument();
  expect(screen.getByText('9 850 ₽')).toBeInTheDocument();
  expect(await screen.findByText('1 200 ₽')).toBeInTheDocument();
  expect(screen.getByText('2 400 ₽')).toBeInTheDocument();
  expect(screen.getByText('🔩 Фильтр × 1')).toBeInTheDocument();
  expect(screen.getByText('450 ₽')).toBeInTheDocument();
  expect(screen.getByText('Работы 3 600 ₽ · запчасти 450 ₽')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Колодки передние/ })).toHaveAttribute('href', '/visits/v1/works/w2');
  expect(screen.getByText(/без исполнителя/)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Петров Иван ›' })).toHaveAttribute('href', '/clients/c1');
});

test('status sheet offers only allowed statuses and patches', async () => {
  mockVisitPage();
  let body: unknown;
  server.use(
    http.patch('/api/visits/v1/status', async ({ request }) => {
      body = await request.json();
      return HttpResponse.json(makeVisit({ status: 'ready', allowed_next_statuses: ['issued', 'cancelled'] }));
    }),
  );
  const { user } = renderApp('/visits/v1', { as: 'master' });
  await user.click(await screen.findByRole('button', { name: 'Сменить статус' }));
  const sheet = screen.getByRole('dialog', { name: 'Сменить статус заезда' });
  expect(within(sheet).getAllByRole('button').map((b) => b.textContent)).toEqual(['Ждём запчасти', 'Готов', 'Отменён', 'Закрыть']);
  await user.click(within(sheet).getByRole('button', { name: 'Готов' }));
  await waitFor(() => expect(body).toEqual({ new_status: 'ready', reason: null }));
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
});

test('409 on status shows the API text in a toast', async () => {
  mockVisitPage();
  server.use(http.patch('/api/visits/v1/status', () => HttpResponse.json({ detail: "Не все работы в статусе 'готово'" }, { status: 409 })));
  const { user } = renderApp('/visits/v1', { as: 'master' });
  await user.click(await screen.findByRole('button', { name: 'Сменить статус' }));
  await user.click(screen.getByRole('button', { name: 'Готов' }));
  expect(await screen.findByText("Не все работы в статусе 'готово'")).toBeInTheDocument();
});

test('cancel asks for a reason', async () => {
  mockVisitPage();
  let body: unknown;
  server.use(
    http.patch('/api/visits/v1/status', async ({ request }) => {
      body = await request.json();
      return HttpResponse.json(makeVisit({ status: 'cancelled', allowed_next_statuses: [] }));
    }),
  );
  const { user } = renderApp('/visits/v1', { as: 'master' });
  await user.click(await screen.findByRole('button', { name: 'Сменить статус' }));
  await user.click(screen.getByRole('button', { name: 'Отменён' }));
  const sheet = screen.getByRole('dialog', { name: 'Отменить заезд' });
  await user.click(within(sheet).getByRole('button', { name: 'Отменить заезд' }));
  expect(within(sheet).getByText('Укажите причину')).toBeInTheDocument();
  expect(body).toBeUndefined();
  await user.type(within(sheet).getByLabelText('Причина отмены'), 'Клиент передумал');
  await user.click(within(sheet).getByRole('button', { name: 'Отменить заезд' }));
  await waitFor(() => expect(body).toEqual({ new_status: 'cancelled', reason: 'Клиент передумал' }));
});

test('cancel sheet forgets the reason and error after it is closed', async () => {
  mockVisitPage();
  const { user } = renderApp('/visits/v1', { as: 'master' });
  await user.click(await screen.findByRole('button', { name: 'Сменить статус' }));
  await user.click(screen.getByRole('button', { name: 'Отменён' }));
  let sheet = screen.getByRole('dialog', { name: 'Отменить заезд' });
  await user.click(within(sheet).getByRole('button', { name: 'Отменить заезд' }));
  await user.type(within(sheet).getByLabelText('Причина отмены'), 'Передумал');
  await user.click(within(sheet).getByRole('button', { name: 'Закрыть' }));
  await user.click(await screen.findByRole('button', { name: 'Сменить статус' }));
  await user.click(screen.getByRole('button', { name: 'Отменён' }));
  sheet = screen.getByRole('dialog', { name: 'Отменить заезд' });
  expect(within(sheet).getByLabelText('Причина отмены')).toHaveValue('');
  expect(within(sheet).queryByText('Укажите причину')).not.toBeInTheDocument();
});

test('unknown visit shows not found', async () => {
  server.use(http.get('/api/visits/nope', () => HttpResponse.json({ detail: 'Visit not found' }, { status: 404 })),
    http.get('/api/visits/nope/lines', () => HttpResponse.json({ detail: 'Visit not found' }, { status: 404 })));
  renderApp('/visits/nope', { as: 'master' });
  expect(await screen.findByText('Заезд не найден')).toBeInTheDocument();
});

function mockPdfLink() {
  server.use(http.post('/api/visits/v1/document/link', () =>
    HttpResponse.json({ url: '/documents/v1/download?token=abc', expires_in: 300 })));
}

test('PDF in Mini App downloads through Telegram with the signed link', async () => {
  const downloadFile = vi.fn();
  (window as { Telegram?: unknown }).Telegram = {
    WebApp: {
      initData: 'x', ready: vi.fn(), expand: vi.fn(), openLink: vi.fn(), downloadFile,
      BackButton: { show: vi.fn(), hide: vi.fn(), onClick: vi.fn(), offClick: vi.fn() },
    },
  };
  mockVisitPage();
  mockPdfLink();
  const { user } = renderApp('/visits/v1', { as: 'master' });
  await user.click(await screen.findByRole('button', { name: 'PDF' }));
  await waitFor(() =>
    expect(downloadFile).toHaveBeenCalledWith({
      url: `${window.location.origin}/api/documents/v1/download?token=abc`,
      file_name: 'zakaz-naryad-А123ВС77.pdf',
    }),
  );
});

test('PDF in a browser starts a plain download of the signed link', async () => {
  const download = vi.spyOn(telegram, 'download').mockImplementation(() => {});
  mockVisitPage();
  mockPdfLink();
  const { user } = renderApp('/visits/v1', { as: 'master' });
  await user.click(await screen.findByRole('button', { name: 'PDF' }));
  await waitFor(() =>
    expect(download).toHaveBeenCalledWith(`${window.location.origin}/api/documents/v1/download?token=abc`, 'zakaz-naryad-А123ВС77.pdf'),
  );
  download.mockRestore();
});

test('works are listed by urgency: in hand, not started, blocked, done', async () => {
  mockVisitPage(makeVisit(), [
    makeWorkLine({ id: 'a', name: 'Готовая', status: 'ready', parts: [] }),
    makeWorkLine({ id: 'b', name: 'Не начатая', status: 'not_ready', parts: [] }),
    makeWorkLine({ id: 'c', name: 'Ждёт', status: 'waiting_parts', parts: [] }),
    makeWorkLine({ id: 'd', name: 'В работе', status: 'in_progress', parts: [] }),
  ]);
  renderApp('/visits/v1', { as: 'master' });
  await screen.findByText('Готовая');
  const names = screen.getAllByRole('link', { name: /Готовая|Не начатая|Ждёт|В работе/ }).map((l) => l.textContent);
  expect(names.map((n) => n!.match(/Готовая|Не начатая|Ждёт|В работе/)![0])).toEqual(['В работе', 'Не начатая', 'Ждёт', 'Готовая']);
});
