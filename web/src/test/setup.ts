import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterAll, afterEach, beforeAll } from 'vitest';
import { clearToken } from '../auth/token';
import { server } from './server';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
  sessionStorage.clear();
  clearToken(); // token.ts keeps an in-memory copy that sessionStorage.clear() does not reset
  delete (window as { Telegram?: unknown }).Telegram;
});
afterAll(() => server.close());
