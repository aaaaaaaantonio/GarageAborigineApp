import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { visitsApi } from '../api/endpoints';
import type { Visit } from '../api/types';
import { useAuth } from '../auth/AuthProvider';
import { Card } from '../ui/Card';
import { EmptyState } from '../ui/EmptyState';
import { Loadable } from '../ui/Loadable';
import { Plate } from '../ui/Plate';
import { ScreenHeader } from '../ui/ScreenHeader';
import { StatusTag } from '../ui/StatusTag';

type Filter = 'all' | 'mine' | 'parts' | 'ready';

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'Все' },
  { key: 'mine', label: 'Мои' },
  { key: 'parts', label: 'Ждут запчасти' },
  { key: 'ready', label: 'Готовы' },
];

function matches(visit: Visit, filter: Filter, userId: string): boolean {
  switch (filter) {
    case 'mine':
      return visit.assigned_master_id === userId;
    case 'parts':
      return visit.status === 'waiting_parts';
    case 'ready':
      return visit.status === 'ready';
    default:
      return true;
  }
}

function VisitCard({ visit }: { visit: Visit }) {
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
      <span className="hint">Мастер: {visit.master_name}</span>
    </Card>
  );
}

export function VisitsScreen() {
  const { user } = useAuth();
  const [filter, setFilter] = useState<Filter>('all');
  const query = useQuery({ queryKey: ['visits', 'active'], queryFn: visitsApi.listActive });
  return (
    <>
      <ScreenHeader title="В работе" right={<Link className="btn btn-primary" to="/visits/new">+ Заезд</Link>} />
      <div className="chips" role="group" aria-label="Фильтр">
        {FILTERS.map((f) => (
          <button key={f.key} type="button" className="chip" aria-pressed={filter === f.key} onClick={() => setFilter(f.key)}>
            {f.label}
          </button>
        ))}
      </div>
      <Loadable query={query}>
        {(data) => {
          const items = data.items.filter((v) => matches(v, filter, user!.id));
          if (items.length === 0) {
            return filter === 'all' ? (
              <EmptyState text="Нет заездов в работе" action={<Link className="btn btn-primary" to="/visits/new">+ Новый заезд</Link>} />
            ) : (
              <EmptyState text="Нет заездов с этим фильтром" />
            );
          }
          return (
            <div className="stack">
              {items.map((v) => <VisitCard key={v.id} visit={v} />)}
              {data.has_more && <p className="hint">Показаны не все заезды</p>}
            </div>
          );
        }}
      </Loadable>
    </>
  );
}
