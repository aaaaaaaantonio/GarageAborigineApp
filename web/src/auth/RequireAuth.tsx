import { Navigate, useLocation } from 'react-router-dom';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';
import { Layout } from '../ui/Layout';
import { useAuth } from './AuthProvider';

export function RequireAuth() {
  const { status, retry } = useAuth();
  const location = useLocation();
  if (status === 'loading') return <div className="loading">Загрузка…</div>;
  if (status === 'error') {
    return (
      <EmptyState text="Нет связи с сервером" action={<Button onClick={retry}>Повторить</Button>} />
    );
  }
  if (status !== 'authed') {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return <Layout />;
}
