import { QueryClient } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MemoryRouter, useLocation } from 'react-router-dom';
import type { Role, User } from '../api/types';
import { AppProviders } from '../App';
import { setToken } from '../auth/token';
import { AppRoutes } from '../routes';
import { server } from './server';

export const USERS: Record<Role, User> = {
  admin: { id: 'u-admin', role: 'admin', full_name: 'Админ Админов', telegram_id: 1, phone: null, branch_id: 'b1' },
  master: { id: 'u-master', role: 'master', full_name: 'Орлов Пётр', telegram_id: 2, phone: null, branch_id: 'b1' },
  mechanic: { id: 'u-mech', role: 'mechanic', full_name: 'Сидоров Иван', telegram_id: 3, phone: null, branch_id: 'b1' },
};

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location" hidden>{location.pathname + location.search}</div>;
}

export function renderApp(path: string, opts: { as?: Role } = {}) {
  if (opts.as) {
    setToken('test-token');
    const me = USERS[opts.as];
    server.use(http.get('/api/auth/me', () => HttpResponse.json(me)));
  }
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const user = userEvent.setup();
  const utils = render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AppProviders queryClient={queryClient}>
        <AppRoutes />
        <LocationProbe />
      </AppProviders>
    </MemoryRouter>,
  );
  return { user, queryClient, ...utils };
}
