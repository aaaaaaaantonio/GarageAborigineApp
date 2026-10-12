import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';

export const server = setupServer(
  http.get('/api/visits', () => HttpResponse.json({ items: [], has_more: false })),
  http.get('/api/work-items/mine', () => HttpResponse.json([])),
  http.get('/api/search/recent', () => HttpResponse.json([])),
);
