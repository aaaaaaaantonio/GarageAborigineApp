import { telegram } from './webapp';

function installWebApp(extra: Record<string, unknown>) {
  const app = {
    initData: 'x', ready: vi.fn(), expand: vi.fn(), openLink: vi.fn(), downloadFile: vi.fn(),
    BackButton: { show: vi.fn(), hide: vi.fn(), onClick: vi.fn(), offClick: vi.fn() },
    ...extra,
  };
  (window as { Telegram?: unknown }).Telegram = { WebApp: app };
  return app;
}

test('download uses downloadFile on Bot API 8.0+', () => {
  const app = installWebApp({ isVersionAtLeast: (v: string) => v === '8.0' });
  telegram.download('https://x/f.pdf', 'f.pdf');
  expect(app.downloadFile).toHaveBeenCalledWith({ url: 'https://x/f.pdf', file_name: 'f.pdf' });
  expect(app.openLink).not.toHaveBeenCalled();
});

test('download falls back to openLink on clients older than 8.0', () => {
  const app = installWebApp({ isVersionAtLeast: () => false });
  telegram.download('https://x/f.pdf', 'f.pdf');
  expect(app.downloadFile).not.toHaveBeenCalled();
  expect(app.openLink).toHaveBeenCalledWith('https://x/f.pdf');
});
