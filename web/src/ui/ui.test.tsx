import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { ApiError } from '../api/client';
import { Button } from './Button';
import { Loadable } from './Loadable';
import { Plate } from './Plate';
import { StatusTag } from './StatusTag';
import { ToastProvider, useToast } from './Toast';

test('busy button is disabled and ignores clicks', async () => {
  const onClick = vi.fn();
  render(<Button busy onClick={onClick}>Сохранить</Button>);
  const btn = screen.getByRole('button', { name: 'Сохранить' });
  expect(btn).toBeDisabled();
  expect(btn).toHaveAttribute('aria-busy', 'true');
  await userEvent.click(btn);
  expect(onClick).not.toHaveBeenCalled();
});

test('plate splits region for russian plates, raw otherwise', () => {
  const { rerender } = render(<Plate value="a123bc77" />);
  expect(screen.getByLabelText('Госномер А123ВС77')).toHaveTextContent('А123ВС77');
  rerender(<Plate value="GX110-6012345" />);
  expect(screen.getByText('GX110-6012345')).toHaveClass('plate-raw');
});

test('status tag shows russian label and tone', () => {
  render(<StatusTag kind="visit" status="waiting_parts" />);
  expect(screen.getByText('Ждём запчасти')).toHaveClass('tag-parts');
});

test('closed visits get their own tones: issued solid green with a check, cancelled red', () => {
  render(<><StatusTag kind="visit" status="issued" /><StatusTag kind="visit" status="cancelled" /></>);
  expect(screen.getByText(/Выдан/)).toHaveClass('tag-issued');
  expect(screen.getByText(/Выдан/)).toHaveTextContent('✓ Выдан');
  expect(screen.getByText('Отменён')).toHaveClass('tag-cancelled');
});

function Harness({ error }: { error: Error }) {
  const query = useQuery({ queryKey: ['x', error.message], queryFn: () => Promise.reject(error), retry: false });
  return <Loadable query={query} notFound="Заезд не найден" backTo="/visits">{() => <p>data</p>}</Loadable>;
}

function renderLoadable(error: Error) {
  const client = new QueryClient();
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Harness error={error} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test('loadable 404 shows not found with a link back', async () => {
  renderLoadable(new ApiError(404, 'Visit not found'));
  expect(await screen.findByText('Заезд не найден')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'К списку' })).toHaveAttribute('href', '/visits');
});

test('loadable 403 shows no access', async () => {
  renderLoadable(new ApiError(403, 'Role not permitted'));
  expect(await screen.findByText('Нет доступа к этому разделу')).toBeInTheDocument();
});

test('loadable network error offers retry', async () => {
  renderLoadable(new ApiError(0, 'Нет связи с сервером'));
  expect(await screen.findByText('Нет связи с сервером')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Повторить' })).toBeInTheDocument();
});

test('toast shows text and retry', async () => {
  const retry = vi.fn();
  function Trigger() {
    const toast = useToast();
    return <button onClick={() => toast.show('Нет связи с сервером', retry)}>go</button>;
  }
  render(<ToastProvider><Trigger /></ToastProvider>);
  await userEvent.click(screen.getByText('go'));
  expect(screen.getByText('Нет связи с сервером')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Повторить' }));
  expect(retry).toHaveBeenCalledOnce();
  expect(screen.queryByText('Нет связи с сервером')).not.toBeInTheDocument();
});
