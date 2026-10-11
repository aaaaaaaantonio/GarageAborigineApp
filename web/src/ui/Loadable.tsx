import type { UseQueryResult } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ApiError } from '../api/client';
import { Button } from './Button';
import { EmptyState } from './EmptyState';

interface Props<T> {
  query: UseQueryResult<T, Error>;
  children: (data: T) => ReactNode;
  notFound?: string;
  backTo?: string;
}

export function Loadable<T>({ query, children, notFound = 'Не найдено', backTo }: Props<T>) {
  if (query.data !== undefined) return <>{children(query.data)}</>;
  if (query.isPending) return <div className="loading" aria-busy="true">Загрузка…</div>;
  const err = query.error;
  if (err instanceof ApiError && err.status === 404) {
    return <EmptyState text={notFound} action={backTo ? <Link className="btn btn-secondary" to={backTo}>К списку</Link> : undefined} />;
  }
  if (err instanceof ApiError && err.status === 403) return <EmptyState text="Нет доступа к этому разделу" />;
  return (
    <EmptyState
      text={err?.message || 'Нет связи с сервером'}
      action={<Button onClick={() => query.refetch()}>Повторить</Button>}
    />
  );
}
