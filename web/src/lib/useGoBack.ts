import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { homePath } from './roles';

export function useGoBack(): () => void {
  const navigate = useNavigate();
  const { user } = useAuth();
  return useCallback(() => {
    const idx = (window.history.state as { idx?: number } | null)?.idx ?? 0;
    if (idx > 0) navigate(-1);
    else navigate(user ? homePath(user.role) : '/', { replace: true });
  }, [navigate, user]);
}
