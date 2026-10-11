import type { Visit } from '../api/types';
import { formatDate } from '../lib/format';
import { Card } from '../ui/Card';
import { EmptyState } from '../ui/EmptyState';
import { StatusTag } from '../ui/StatusTag';

export function VisitHistory({ visits }: { visits: Visit[] }) {
  if (visits.length === 0) return <EmptyState text="Заездов нет" />;
  return (
    <div className="stack">
      {visits.map((v) => (
        <Card key={v.id} to={`/visits/${v.id}`}>
          <div className="row">
            <span>{formatDate(v.created_at)} · {v.make_model}</span>
            <StatusTag kind="visit" status={v.status} />
          </div>
        </Card>
      ))}
    </div>
  );
}
