import { useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { ROOT_PATHS } from '../lib/roles';
import { useGoBack } from '../lib/useGoBack';
import { telegram } from '../telegram/webapp';
import { TabBar } from './TabBar';

export function Layout() {
  const { pathname } = useLocation();
  const goBack = useGoBack();
  useEffect(() => {
    if (ROOT_PATHS.includes(pathname)) return;
    return telegram.showBack(goBack);
  }, [pathname, goBack]);
  return (
    <div className="app">
      <main className="app-main">
        <Outlet />
      </main>
      <TabBar />
    </div>
  );
}
