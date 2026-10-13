import { useQuery } from '@tanstack/react-query';
import { workItemsApi } from '../api/endpoints';
import { formatDate } from '../lib/format';
import { Card } from '../ui/Card';
import { EmptyState } from '../ui/EmptyState';
import { Loadable } from '../ui/Loadable';
import { Plate } from '../ui/Plate';
import { ScreenHeader } from '../ui/ScreenHeader';
import { StatusTag } from '../ui/StatusTag';

/** The mechanic's finished work in closed visits. Read-only: the car has left the shop. */
export function DoneWorksScreen() {
  const query = useQuery({ queryKey: ['doneWorks'], queryFn: workItemsApi.done });
  return (
    <>
      <ScreenHeader title="Выполненные работы" />
      <Loadable query={query}>
        {(items) =>
          items.length === 0 ? (
            <EmptyState text="Выполненных работ пока нет" />
          ) : (
            <div className="stack">
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
                    <span className="hint">{formatDate(w.visit_date)}</span>
                  </div>
                </Card>
              ))}
            </div>
          )
        }
      </Loadable>
    </>
  );
}
