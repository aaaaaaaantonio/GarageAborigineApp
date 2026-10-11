// Thin wrapper over https://telegram.org/js/telegram-web-app.js. In a plain browser
// the script still defines WebApp but initData is empty — every call is a no-op then.
interface TelegramWebApp {
  initData: string;
  ready(): void;
  expand(): void;
  setHeaderColor?(color: string): void;
  setBackgroundColor?(color: string): void;
  BackButton: { show(): void; hide(): void; onClick(cb: () => void): void; offClick(cb: () => void): void };
  HapticFeedback?: { notificationOccurred(kind: 'success' | 'error' | 'warning'): void };
  openLink(url: string): void;
  /** Bot API 8.0+; older clients lack it. */
  downloadFile?(params: { url: string; file_name: string }): void;
}

function webApp(): TelegramWebApp | null {
  const app = (window as { Telegram?: { WebApp?: TelegramWebApp } }).Telegram?.WebApp;
  return app && app.initData ? app : null;
}

export const telegram = {
  isMiniApp: (): boolean => webApp() !== null,
  initData: (): string => webApp()?.initData ?? '',
  init(): void {
    const app = webApp();
    if (!app) return;
    app.ready();
    app.expand();
    app.setHeaderColor?.('#1d2024');
    app.setBackgroundColor?.('#1d2024');
  },
  showBack(onClick: () => void): () => void {
    const app = webApp();
    if (!app) return () => {};
    app.BackButton.onClick(onClick);
    app.BackButton.show();
    return () => {
      app.BackButton.offClick(onClick);
      app.BackButton.hide();
    };
  },
  haptic(kind: 'success' | 'error'): void {
    webApp()?.HapticFeedback?.notificationOccurred(kind);
  },
  /** Save a file from a URL that needs no Authorization header (e.g. a signed PDF link). */
  download(url: string, fileName: string): void {
    const app = webApp();
    if (app?.downloadFile) app.downloadFile({ url, file_name: fileName });
    else if (app) app.openLink(url);
    else window.location.assign(url);
  },
};
