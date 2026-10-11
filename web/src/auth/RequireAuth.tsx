import { Navigate, useLocation } from 'react-router-dom';
import { Layout } from '../ui/Layout';
import { useAuth } from './AuthProvider';

export function RequireAuth() {
  const { status } = useAuth();
  const location = useLocation();
  if (status === 'loading') return <div className="loading">Загрузка…</div>;
  if (status !== 'authed') {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return <Layout />;
}
