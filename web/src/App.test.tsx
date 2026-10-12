import { screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { server } from './test/server';
import { renderApp } from './test/render';

test('renders the brand on the login screen', async () => {
  server.use(http.get('/api/auth/dev-users', () => HttpResponse.json([])));
  renderApp('/login');
  expect(await screen.findByText(/Гараж/)).toBeInTheDocument();
});
