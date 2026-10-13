import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { workItemsApi } from '../api/endpoints';
import { formatDate, formatHours } from '../lib/format';
import { PERIOD_LABELS, sinceFor, type Period } from '../lib/periods';
import { Card } from '../ui/Card';
import { Picker } from '../ui/Picker';
import { EmptyState } from '../ui/EmptyState';
import { Loadable } from '../ui/Loadable';
import { Plate } from '../ui/Plate';
import { ScreenHeader } from '../ui/ScreenHeader';
import { StatusTag } from '../ui/StatusTag';

type Outcome = 'all' | 'issued' | 'cancelled';

const PERIODS = (['week', 'month', 'all'] as Period[]).map((p) => ({ value: p, label: PERIOD_LABELS[p] }));
const OUTCOMES: { value: Outcome; label: string }[] = [
  { value: 'all', label: 'Все' },
  { value: 'issued', label: 'Выданы' },
  { value: 'cancelled', label: 'Отменены' },
];

/** The mechanic's finished work in closed visits. Read-only: the car has left the shop. */
export function DoneWorksScreen() {
  const [period, setPeriod] = useState<Period>('month');
  const [outcome, setOutcome] = useState<Outcome>('all');
  const query = useQuery({
    // `period`, not `since`: since moves with the clock and would refetch on every render.
    queryKey: ['doneWorks', period, outcome],
    queryFn: () => workItemsApi.done({ since: sinceFor(period), outcome: outcome === 'all' ? undefined : outcome }),
    placeholderData: keepPreviousData,
  });
  return (
    <>
      <ScreenHeader title="Выполненные работы" />
      <div className="filters-row">
        <Picker label="Период" value={period} options={PERIODS} onChange={setPeriod} />
        <Picker label="Итог" value={outcome} options={OUTCOMES} onChange={setOutcome} />
      </div>
      <Loadable query={query}>
        {({ items, count, total_norm_hours, has_more }) =>
          items.length === 0 ? (
            <EmptyState text="Выполненных работ пока нет" />
          ) : (
            <div className="stack">
              <div className="card">
                <b>Работ: {count} · {formatHours(total_norm_hours)}</b>
              </div>
              {items.map((w) => (
                <Card key={w.id}>
                  <div className="row">
                    <span>{w.name}</span>
                    <StatusTag kind="visit" status={w.visit_status} />
                  </div>
                  <div className="row">
                    {w.plate_number ? (
                      <span>
                        <Plate value={w.plate_number} /> <span className="hint">{w.make_model}</span>
                      </span>
                    ) : (
                      <span />
                    )}
                    <span className="hint">{formatDate(w.closed_at)}</span>
                  </div>
                </Card>
              ))}
              {has_more && <p className="hint">Показаны последние {items.length}</p>}
            </div>
          )
        }
      </Loadable>
    </>
  );
}
