import { useMutation, useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { ApiError } from '../api/client';
import { authApi } from '../api/endpoints';
import type { AuthResponse } from '../api/types';
import { useAuth } from '../auth/AuthProvider';
import { ROLE_LABELS } from '../lib/labels';
import { homePath } from '../lib/roles';
import { telegram } from '../telegram/webapp';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';

function Brand() {
  return <div className="brand">Гараж <b>·</b> CRM</div>;
}

function TelegramLogin({ onSignedIn }: { onSignedIn: (r: AuthResponse) => void }) {
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    authApi
      .telegram(telegram.initData())
      .then((r) => !cancelled && onSignedIn(r))
      .catch((e) => !cancelled && setError(e instanceof ApiError ? e.message : 'Не удалось войти'));
    return () => {
      cancelled = true;
    };
  }, [onSignedIn]);
  return error ? <EmptyState text={error} /> : <div className="loading">Вход…</div>;
}

function DevLogin({ onSignedIn }: { onSignedIn: (r: AuthResponse) => void }) {
  const users = useQuery({ queryKey: ['devUsers'], queryFn: authApi.devUsers, retry: false });
  const login = useMutation({ mutationFn: authApi.devLogin, onSuccess: onSignedIn });
  if (users.isPending) return <div className="loading">Загрузка…</div>;
  if (users.isError) return <EmptyState text="Откройте приложение из Telegram" />;
  return (
    <div className="stack">
      <p className="hint">Режим разработки: войти как сотрудник</p>
      {users.data.map((u) => (
        <Button key={u.id} block busy={login.isPending && login.variables === u.id} disabled={login.isPending} onClick={() => login.mutate(u.id)}>
          {u.full_name} · {ROLE_LABELS[u.role]}
        </Button>
      ))}
      {login.isError && <p className="form-error">{login.error.message}</p>}
    </div>
  );
}

export function LoginScreen() {
  const { status, user, signIn } = useAuth();
  const location = useLocation();
  if (status === 'authed' && user) {
    const from = (location.state as { from?: string } | null)?.from;
    return <Navigate to={from && from !== '/login' ? from : homePath(user.role)} replace />;
  }
  return (
    <div className="login">
      <Brand />
      {status === 'loading' ? (
        <div className="loading">Загрузка…</div>
      ) : telegram.isMiniApp() ? (
        <TelegramLogin onSignedIn={signIn} />
      ) : (
        <DevLogin onSignedIn={signIn} />
      )}
    </div>
  );
}
