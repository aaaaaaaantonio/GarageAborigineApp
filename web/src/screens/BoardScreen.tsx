import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { usersApi, workItemsApi } from '../api/endpoints';
import type { BoardGroup, BoardItem, BoardParams, WorkCategory, WorkItemStatus } from '../api/types';
import { WORK_CATEGORY_LABELS, WORK_STATUS_ICONS, WORK_STATUS_LABELS, assigneeLabel } from '../lib/labels';
import { Card } from '../ui/Card';
import { Picker } from '../ui/Picker';
import { EmptyState } from '../ui/EmptyState';
import { Loadable } from '../ui/Loadable';
import { Plate } from '../ui/Plate';
import { ScreenHeader } from '../ui/ScreenHeader';
import { SelectField } from '../ui/SelectField';
import { StatusTag } from '../ui/StatusTag';

const STATUSES: { value: WorkItemStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'Все' },
  { value: 'not_ready', label: 'Не начаты' },
  { value: 'in_progress', label: 'В работе' },
  { value: 'waiting_parts', label: 'Ждут запчасти' },
  { value: 'ready', label: 'Готовы' },
];
const GROUPS: { value: BoardGroup; label: string }[] = [
  { value: 'mechanic', label: 'По механику' },
  { value: 'status', label: 'По статусу' },
  { value: 'car', label: 'По машине' },
];
const APPROVALS: { value: 'all' | 'unapproved'; label: string }[] = [
  { value: 'all', label: 'Все работы' },
  { value: 'unapproved', label: 'Только не согласованные' },
];
const CATEGORIES = [
  { value: '', label: 'Все категории' },
  ...(Object.keys(WORK_CATEGORY_LABELS) as WorkCategory[]).map((c) => ({ value: c, label: WORK_CATEGORY_LABELS[c] })),
];

function groupTitle(item: BoardItem, group: BoardGroup): string {
  if (group === 'status') return WORK_STATUS_LABELS[item.status];
  if (group === 'car') return `${item.plate_number ?? '—'} · ${item.make_model ?? ''}`.trim();
  return item.assigned_mechanic_name ?? 'Без исполнителя';
}

/** Server returns items ordered by the group, so equal titles are adjacent. */
function grouped(items: BoardItem[], group: BoardGroup): [string, BoardItem[]][] {
  const out: [string, BoardItem[]][] = [];
  for (const item of items) {
    const title = groupTitle(item, group);
    if (out.length && out[out.length - 1][0] === title) out[out.length - 1][1].push(item);
    else out.push([title, [item]]);
  }
  return out;
}

/** Every work item of open visits: who is doing what. */
export function BoardScreen() {
  const [mechanic, setMechanic] = useState('');
  const [status, setStatus] = useState<WorkItemStatus | 'all'>('all');
  const [category, setCategory] = useState('');
  const [approval, setApproval] = useState<'all' | 'unapproved'>('all');
  const [group, setGroup] = useState<BoardGroup>('mechanic');
  const mechanics = useQuery({ queryKey: ['mechanics'], queryFn: usersApi.mechanics });
  const params: BoardParams = {
    mechanic_id: mechanic && mechanic !== 'none' ? mechanic : undefined,
    unassigned: mechanic === 'none',
    status: status === 'all' ? undefined : [status],
    category: category ? [category as WorkCategory] : undefined,
    unapproved: approval === 'unapproved',
    group,
  };
  const query = useQuery({ queryKey: ['board', params], queryFn: () => workItemsApi.board(params), placeholderData: keepPreviousData });
  return (
    <>
      <ScreenHeader title="Доска работ" back />
      <div className="filters-row">
        <Picker label="Статус работы" value={status} options={STATUSES} onChange={setStatus} />
        <SelectField
          label="Механик"
          value={mechanic}
          options={[
            { value: '', label: 'Все механики' },
            { value: 'none', label: 'Без исполнителя' },
            ...(mechanics.data ?? []).map((m) => ({ value: m.id, label: assigneeLabel(m) })),
          ]}
          onChange={(e) => setMechanic(e.target.value)}
        />
        <SelectField label="Категория" value={category} options={CATEGORIES} onChange={(e) => setCategory(e.target.value)} />
        <Picker label="Согласование" value={approval} options={APPROVALS} onChange={setApproval} />
        <Picker label="Группировка" value={group} options={GROUPS} onChange={setGroup} />
      </div>
      <Loadable query={query}>
        {(data) =>
          data.items.length === 0 ? (
            <EmptyState text="Работ с этим фильтром нет" />
          ) : (
            <div className="stack">
              {grouped(data.items, group).map(([title, items]) => (
                <section key={title} className="stack">
                  <h2 className="section-title">{title}</h2>
                  {items.map((w) => (
                    <Card key={w.id} to={`/visits/${w.visit_id}/works/${w.id}`}>
                      <div className="row">
                        <span>
                          <span aria-hidden="true">{WORK_STATUS_ICONS[w.status]} </span>
                          {w.name}
                        </span>
                        <StatusTag kind="work" status={w.status} />
                      </div>
                      <div className="row">
                        {group !== 'car' && w.plate_number ? <Plate value={w.plate_number} /> : <span />}
                        <span className="hint">
                          {group !== 'mechanic' && (w.assigned_mechanic_name ?? 'без исполнителя')}
                          {!w.approved_by_client && (group !== 'mechanic' ? ' · ' : '')}
                          {!w.approved_by_client && 'не согласовано'}
                        </span>
                      </div>
                    </Card>
                  ))}
                </section>
              ))}
              {data.has_more && <p className="hint">Показаны первые {data.items.length}</p>}
            </div>
          )
        }
      </Loadable>
    </>
  );
}
