import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { workItemsApi } from '../api/endpoints';
import type { MineSort, MyWorkItem, WorkItemStatus } from '../api/types';
import { WORK_STATUS_ICONS } from '../lib/labels';
import { Card } from '../ui/Card';
import { Picker } from '../ui/Picker';
import { EmptyState } from '../ui/EmptyState';
import { Loadable } from '../ui/Loadable';
import { Plate } from '../ui/Plate';
import { ScreenHeader } from '../ui/ScreenHeader';
import { StatusTag } from '../ui/StatusTag';

const STATUSES: { value: WorkItemStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'Все' },
  { value: 'in_progress', label: 'В работе' },
  { value: 'not_ready', label: 'Не начаты' },
  { value: 'waiting_parts', label: 'Ждут запчасти' },
  { value: 'ready', label: 'Готовы' },
];
const SORTS: { value: MineSort; label: string }[] = [
  { value: 'urgency', label: 'По срочности' },
  { value: 'car', label: 'По машинам' },
];

function WorkCard({ work, withCar }: { work: MyWorkItem; withCar: boolean }) {
  return (
    <Card to={`/visits/${work.visit_id}/works/${work.id}`}>
      <div className="row">
        <span>
          <span aria-hidden="true">{WORK_STATUS_ICONS[work.status]} </span>
          {work.name}
        </span>
        <StatusTag kind="work" status={work.status} />
      </div>
      {withCar && work.plate_number && (
        <div className="row">
          <Plate value={work.plate_number} />
          <span className="hint">{work.make_model}</span>
        </div>
      )}
    </Card>
  );
}

/** The server keeps a car's works together in `car` mode; split them at each new visit. */
function byCar(items: MyWorkItem[]): MyWorkItem[][] {
  const groups: MyWorkItem[][] = [];
  for (const w of items) {
    const current = groups[groups.length - 1];
    if (current && current[0].visit_id === w.visit_id) current.push(w);
    else groups.push([w]);
  }
  return groups;
}

export function MyWorksScreen() {
  const [status, setStatus] = useState<WorkItemStatus | 'all'>('all');
  const [sort, setSort] = useState<MineSort>('urgency');
  const params = { status: status === 'all' ? undefined : [status], sort };
  const query = useQuery({ queryKey: ['myWorks', params], queryFn: () => workItemsApi.mine(params), placeholderData: keepPreviousData });
  return (
    <>
      <ScreenHeader title="Мои работы" />
      <div className="filters-row">
        <Picker label="Статус" value={status} options={STATUSES} onChange={setStatus} />
        <Picker label="Порядок" value={sort} options={SORTS} onChange={setSort} />
      </div>
      <Loadable query={query}>
        {(items) =>
          items.length === 0 ? (
            <EmptyState text={status === 'all' ? 'Нет назначенных работ' : 'Нет работ с этим фильтром'} />
          ) : sort === 'car' ? (
            <div className="stack">
              {byCar(items).map((group) => (
                <section key={group[0].visit_id} className="stack">
                  <h2 className="section-title">{`${group[0].plate_number ?? '—'} · ${group[0].make_model ?? ''}`.trim()}</h2>
                  {group.map((w) => <WorkCard key={w.id} work={w} withCar={false} />)}
                </section>
              ))}
            </div>
          ) : (
            <div className="stack">
              {items.map((w) => <WorkCard key={w.id} work={w} withCar />)}
            </div>
          )
        }
      </Loadable>
    </>
  );
}
