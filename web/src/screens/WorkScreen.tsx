import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { usersApi, workItemsApi } from '../api/endpoints';
import type { MyWorkItem, WorkItem, WorkItemStatus } from '../api/types';
import { useAuth } from '../auth/AuthProvider';
import { WORK_STATUS_ICONS, WORK_STATUS_LABELS } from '../lib/labels';
import { useAction } from '../lib/useAction';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';
import { Loadable } from '../ui/Loadable';
import { Plate } from '../ui/Plate';
import { ScreenHeader } from '../ui/ScreenHeader';
import { Sheet } from '../ui/Sheet';
import { StatusTag } from '../ui/StatusTag';

type AnyWork = WorkItem | MyWorkItem;

function isStaffItem(w: AnyWork): w is WorkItem {
  return 'approved_by_client' in w;
}

export function WorkScreen() {
  const { visitId = '', itemId = '' } = useParams();
  const { user } = useAuth();
  const isMechanic = user!.role === 'mechanic';
  const [assignOpen, setAssignOpen] = useState(false);
  const query = useQuery<AnyWork[], Error>({
    queryKey: isMechanic ? ['myWorks'] : ['workItems', visitId],
    queryFn: () => (isMechanic ? workItemsApi.mine() : workItemsApi.list(visitId)),
  });
  const mechanics = useQuery({ queryKey: ['mechanics'], queryFn: usersApi.mechanics, enabled: assignOpen });
  const invalidate = [['workItems', visitId], ['myWorks'], ['visit', visitId], ['visitLines', visitId]];
  const status = useAction((s: WorkItemStatus) => workItemsApi.changeStatus(visitId, itemId, s), { invalidate });
  const approve = useAction(() => workItemsApi.approve(visitId, itemId), { invalidate });
  const assign = useAction((mechanicId: string | null) => workItemsApi.assign(visitId, itemId, mechanicId), {
    invalidate,
    onSuccess: () => setAssignOpen(false),
  });
  const busy = status.isPending || approve.isPending || assign.isPending;

  return (
    <>
      <ScreenHeader title="Работа" back />
      <Loadable query={query}>
        {(items) => {
          const w = items.find((x) => x.id === itemId);
          if (!w) return <EmptyState text="Работа не найдена" />;
          return (
            <div className="stack">
              <div className="card">
                <div className="row">
                  <b>{w.name}</b>
                  <StatusTag kind="work" status={w.status} />
                </div>
                {!isStaffItem(w) && w.plate_number && (
                  <div className="row">
                    <Plate value={w.plate_number} />
                    <span className="hint">{w.make_model}</span>
                  </div>
                )}
                {isStaffItem(w) && (
                  <>
                    <span className="hint">Исполнитель: {w.assigned_mechanic_name ?? 'не назначен'}</span>
                    <span className="hint">{w.approved_by_client ? '✅ Согласовано клиентом' : 'Не согласовано клиентом'}</span>
                  </>
                )}
              </div>
              {w.allowed_next_statuses.length > 0 && (
                <>
                  <h2 className="section-title">Статус</h2>
                  {w.allowed_next_statuses.map((s) => (
                    <Button key={s} block busy={status.isPending && status.variables === s} disabled={busy} onClick={() => status.mutate(s)}>
                      {WORK_STATUS_ICONS[s]} {WORK_STATUS_LABELS[s]}
                    </Button>
                  ))}
                </>
              )}
              {!isMechanic && isStaffItem(w) && (
                <>
                  <h2 className="section-title">Действия</h2>
                  {!w.approved_by_client && (
                    <Button variant="primary" block busy={approve.isPending} disabled={busy} onClick={() => approve.mutate()}>
                      Согласовано клиентом
                    </Button>
                  )}
                  <Link className="btn btn-block" to={`/visits/${visitId}/works/${itemId}/parts/new`}>+ Запчасть</Link>
                  <Button block disabled={busy} onClick={() => setAssignOpen(true)}>Сменить исполнителя</Button>
                </>
              )}
              <Sheet open={assignOpen} title="Кому передать работу?" onClose={() => setAssignOpen(false)}>
                <Loadable query={mechanics}>
                  {(list) => (
                    <>
                      {list.map((m) => (
                        <Button key={m.id} block busy={assign.isPending && assign.variables === m.id} disabled={assign.isPending} onClick={() => assign.mutate(m.id)}>
                          {m.full_name}
                        </Button>
                      ))}
                      <Button block variant="ghost" disabled={assign.isPending} onClick={() => assign.mutate(null)}>Без исполнителя</Button>
                    </>
                  )}
                </Loadable>
              </Sheet>
            </div>
          );
        }}
      </Loadable>
    </>
  );
}
