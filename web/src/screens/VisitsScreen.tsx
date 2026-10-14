import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { usersApi, visitsApi } from '../api/endpoints';
import type { Visit, VisitListParams, VisitSort } from '../api/types';
import { useAuth } from '../auth/AuthProvider';
import { daysSince } from '../lib/format';
import { Card } from '../ui/Card';
import { Picker } from '../ui/Picker';
import { EmptyState } from '../ui/EmptyState';
import { Loadable } from '../ui/Loadable';
import { Plate } from '../ui/Plate';
import { ScreenHeader } from '../ui/ScreenHeader';
import { SelectField } from '../ui/SelectField';
import { StatusTag } from '../ui/StatusTag';

type Filter = 'all' | 'mine' | 'approval' | 'parts' | 'ready' | 'unassigned' | 'stale';

const FILTERS: { value: Filter; label: string }[] = [
  { value: 'all', label: 'Все' },
  { value: 'mine', label: 'Мои' },
  { value: 'approval', label: 'Согласование' },
  { value: 'parts', label: 'Ждут запчасти' },
  { value: 'ready', label: 'Готовы' },
  { value: 'unassigned', label: 'Без механика' },
  { value: 'stale', label: 'Долго стоят' },
];

const SORTS: { value: VisitSort; label: string }[] = [
  { value: 'date', label: 'По дате приёма' },
  { value: 'stale', label: 'Долго стоят' },
  { value: 'status', label: 'По статусу' },
];

function filterParams(filter: Filter, userId: string): VisitListParams {
  switch (filter) {
    case 'mine':
      return { master_id: userId };
    case 'approval':
      return { status: ['approval'] };
    case 'parts':
      return { status: ['waiting_parts'] };
    case 'ready':
      return { status: ['ready'] };
    case 'unassigned':
      return { unassigned_work: true };
    case 'stale':
      return { stale: true };
    default:
      return {};
  }
}

function VisitCard({ visit }: { visit: Visit }) {
  const days = daysSince(visit.last_activity_at);
  return (
    <Card to={`/visits/${visit.id}`}>
      <div className="row">
        <Plate value={visit.plate_number} />
        <StatusTag kind="visit" status={visit.status} />
      </div>
      <div className="row">
        <span>{visit.make_model}</span>
        <span className="hint">{visit.client_name}</span>
      </div>
      <div className="row">
        <span className="hint">Мастер: {visit.master_name}</span>
        {days >= 1 && <span className="hint">{days} дн. без движения</span>}
      </div>
    </Card>
  );
}

export function VisitsScreen() {
  const { user } = useAuth();
  const isAdmin = user!.role === 'admin';
  const [filter, setFilter] = useState<Filter>('all');
  const [sort, setSort] = useState<VisitSort>('date');
  const [masterId, setMasterId] = useState('');
  const masters = useQuery({ queryKey: ['masters'], queryFn: usersApi.masters, enabled: isAdmin });
  // Assigned masters are always MASTER, so an admin has no "mine".
  const filters = isAdmin ? FILTERS.filter((f) => f.value !== 'mine') : FILTERS;
  const params: VisitListParams = {
    active: true,
    ...filterParams(filter, user!.id),
    ...(isAdmin && masterId ? { master_id: masterId } : {}),
    sort,
  };
  const query = useQuery({
    queryKey: ['visits', 'active', params],
    queryFn: () => visitsApi.list(params),
    placeholderData: keepPreviousData,
  });
  const unfiltered = filter === 'all' && !masterId;
  return (
    <>
      <ScreenHeader title="В работе" />
      <div className="row links-row">
        <Link className="btn" to="/works">Доска работ</Link>
        <Link className="btn" to="/visits/archive">Архив</Link>
      </div>
      <div className="filters-row">
        <Picker label="Фильтр" value={filter} options={filters} onChange={setFilter} />
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
      <Loadable query={query}>
        {(data) => {
          if (data.items.length === 0) {
            return unfiltered ? (
              <EmptyState text="Нет заездов в работе" action={<Link className="btn btn-primary" to="/visits/new">+ Новый заезд</Link>} />
            ) : (
              <EmptyState text="Нет заездов с этим фильтром" />
            );
          }
          return (
            <div className="stack">
              {data.items.map((v) => <VisitCard key={v.id} visit={v} />)}
              {data.has_more && <p className="hint">Показаны {data.items.length} из {data.total_count}</p>}
            </div>
          );
        }}
      </Loadable>
    </>
  );
}
