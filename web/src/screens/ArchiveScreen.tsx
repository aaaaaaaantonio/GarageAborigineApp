import { keepPreviousData, useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { usersApi, visitsApi } from '../api/endpoints';
import type { VisitListParams, VisitSort } from '../api/types';
import { useAuth } from '../auth/AuthProvider';
import { formatDate, formatRub } from '../lib/format';
import { PERIOD_LABELS, sinceFor, type Period } from '../lib/periods';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { Picker } from '../ui/Picker';
import { EmptyState } from '../ui/EmptyState';
import { Plate } from '../ui/Plate';
import { ScreenHeader } from '../ui/ScreenHeader';
import { SelectField } from '../ui/SelectField';
import { StatusTag } from '../ui/StatusTag';

type Outcome = 'all' | 'issued' | 'cancelled';

const PERIODS = (['week', 'month', 'quarter', 'all'] as Period[]).map((p) => ({ value: p, label: PERIOD_LABELS[p] }));
const OUTCOMES: { value: Outcome; label: string }[] = [
  { value: 'all', label: 'Все' },
  { value: 'issued', label: 'Выданы' },
  { value: 'cancelled', label: 'Отменены' },
];
const SORTS: { value: VisitSort; label: string }[] = [
  { value: 'date', label: 'По дате' },
  { value: 'amount', label: 'По сумме' },
];

/** Closed visits (issued and cancelled) with period totals. */
export function ArchiveScreen() {
  const { user } = useAuth();
  const isAdmin = user!.role === 'admin';
  const [period, setPeriod] = useState<Period>('month');
  const [outcome, setOutcome] = useState<Outcome>('all');
  const [sort, setSort] = useState<VisitSort>('date');
  const [masterId, setMasterId] = useState('');
  const masters = useQuery({ queryKey: ['masters'], queryFn: usersApi.masters, enabled: isAdmin });
  const since = sinceFor(period);
  const params: VisitListParams = {
    closed: true,
    since,
    status: outcome === 'all' ? undefined : [outcome],
    master_id: masterId || undefined,
    sort,
  };
  const query = useInfiniteQuery({
    // `period`, not `since`: since moves with the clock and would refetch on every render.
    queryKey: ['visits', 'archive', { ...params, since: period }],
    queryFn: ({ pageParam }) => visitsApi.list({ ...params, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (lastPage, pages) => (lastPage.has_more ? pages.reduce((n, p) => n + p.items.length, 0) : undefined),
    placeholderData: keepPreviousData,
  });
  const first = query.data?.pages[0];
  const visits = query.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <>
      <ScreenHeader title="Архив заездов" back />
      <div className="filters-row">
        <Picker label="Период" value={period} options={PERIODS} onChange={setPeriod} />
        <Picker label="Итог" value={outcome} options={OUTCOMES} onChange={setOutcome} />
        <Picker label="Сортировка" value={sort} options={SORTS} onChange={setSort} />
        {isAdmin && (
          <SelectField
            label="Мастер"
            value={masterId}
            options={[{ value: '', label: 'Все мастера' }, ...(masters.data ?? []).map((m) => ({ value: m.id, label: m.full_name }))]}
            onChange={(e) => setMasterId(e.target.value)}
          />
        )}
      </div>
      {first === undefined ? (
        query.isError ? (
          <EmptyState text={query.error.message || 'Нет связи с сервером'} action={<Button onClick={() => query.refetch()}>Повторить</Button>} />
        ) : (
          <div className="loading" aria-busy="true">Загрузка…</div>
        )
      ) : visits.length === 0 ? (
        <EmptyState text="За этот период закрытых заездов нет" />
      ) : (
        <div className="stack">
          <div className="card">
            <b>Заездов: {first.total_count} · Выручка: {formatRub(first.issued_amount)}</b>
          </div>
          {visits.map((v) => (
            <Card key={v.id} to={`/visits/${v.id}`}>
              <div className="row">
                <Plate value={v.plate_number} />
                <StatusTag kind="visit" status={v.status} />
              </div>
              <div className="row">
                <span>{v.make_model}</span>
                <span className="hint">{v.client_name}</span>
              </div>
              <div className="row">
                <span className="hint">{formatDate(v.status_changed_at)} · {v.master_name}</span>
                <span className="mono">{formatRub(v.total_amount)}</span>
              </div>
            </Card>
          ))}
          {query.hasNextPage && (
            <Button variant="ghost" block onClick={() => query.fetchNextPage()} disabled={query.isFetchingNextPage}>
              Показать ещё
            </Button>
          )}
        </div>
      )}
    </>
  );
}
