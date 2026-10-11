import { useQueryClient } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { ApiError, onUnauthorized } from '../api/client';
import { authApi } from '../api/endpoints';
import type { AuthResponse, User } from '../api/types';
import { clearToken, getToken, setToken } from './token';

/** 'error': the session check failed for a reason other than 401 — the token is kept, retry is offered. */
type Status = 'loading' | 'anon' | 'authed' | 'error';

interface AuthContextValue {
  status: Status;
  user: User | null;
  signIn(response: AuthResponse): void;
  signOut(): void;
  retry(): void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<{ status: Status; user: User | null }>(() => ({
    status: getToken() ? 'loading' : 'anon',
    user: null,
  }));

  const signIn = useCallback(
    (response: AuthResponse) => {
      queryClient.clear();
      setToken(response.token);
      setState({ status: 'authed', user: response.user });
    },
    [queryClient],
  );

  const signOut = useCallback(() => {
    clearToken();
    queryClient.clear();
    setState({ status: 'anon', user: null });
  }, [queryClient]);

  useEffect(() => {
    onUnauthorized(() => setState({ status: 'anon', user: null }));
  }, []);

  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => {
    setState({ status: 'loading', user: null });
    setAttempt((n) => n + 1);
  }, []);

  useEffect(() => {
    if (!getToken()) return;
    let cancelled = false;
    authApi
      .me()
      .then((user) => !cancelled && setState({ status: 'authed', user }))
      .catch((e) => {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 401) {
          clearToken();
          setState({ status: 'anon', user: null });
        } else {
          setState({ status: 'error', user: null });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const value = useMemo(() => ({ ...state, signIn, signOut, retry }), [state, signIn, signOut, retry]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth outside AuthProvider');
  return ctx;
}
