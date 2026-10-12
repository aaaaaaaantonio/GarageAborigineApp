import { useQuery } from '@tanstack/react-query';
import { workItemsApi } from '../api/endpoints';
import { WORK_STATUS_ICONS } from '../lib/labels';
import { Card } from '../ui/Card';
import { EmptyState } from '../ui/EmptyState';
import { Loadable } from '../ui/Loadable';
import { Plate } from '../ui/Plate';
import { ScreenHeader } from '../ui/ScreenHeader';
import { StatusTag } from '../ui/StatusTag';

export function MyWorksScreen() {
  const query = useQuery({ queryKey: ['myWorks'], queryFn: workItemsApi.mine });
  return (
    <>
      <ScreenHeader title="Мои работы" />
      <Loadable query={query}>
        {(items) =>
          items.length === 0 ? (
            <EmptyState text="Нет назначенных работ" />
          ) : (
            <div className="stack">
              {items.map((w) => (
                <Card key={w.id} to={`/visits/${w.visit_id}/works/${w.id}`}>
                  <div className="row">
                    <span>
                      <span aria-hidden="true">{WORK_STATUS_ICONS[w.status]} </span>
                      {w.name}
                    </span>
                    <StatusTag kind="work" status={w.status} />
                  </div>
                  {w.plate_number && (
                    <div className="row">
                      <Plate value={w.plate_number} />
                      <span className="hint">{w.make_model}</span>
                    </div>
                  )}
                </Card>
              ))}
            </div>
          )
        }
      </Loadable>
    </>
  );
}
