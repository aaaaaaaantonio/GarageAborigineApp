import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { visitsApi } from '../api/endpoints';
import type { VisitStatus } from '../api/types';
import { CancelVisitSheet } from '../forms/CancelVisitSheet';
import { formatKm, formatRub } from '../lib/format';
import { VISIT_STATUS_LABELS, WORK_STATUS_ICONS } from '../lib/labels';
import { useAction } from '../lib/useAction';
import { telegram } from '../telegram/webapp';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';
import { Loadable } from '../ui/Loadable';
import { Plate } from '../ui/Plate';
import { ScreenHeader } from '../ui/ScreenHeader';
import { Sheet } from '../ui/Sheet';
import { StatusTag } from '../ui/StatusTag';

export function VisitScreen() {
  const { visitId = '' } = useParams();
  const visit = useQuery({ queryKey: ['visit', visitId], queryFn: () => visitsApi.get(visitId) });
  const lines = useQuery({ queryKey: ['visitLines', visitId], queryFn: () => visitsApi.lines(visitId) });
  const [statusOpen, setStatusOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const changeStatus = useAction((status: VisitStatus) => visitsApi.changeStatus(visitId, status), {
    invalidate: [['visit', visitId], ['visits']],
    onSuccess: () => setStatusOpen(false),
  });
  const pdf = useAction(() => visitsApi.documentLink(visitId), {
    onSuccess: ({ url }) =>
      telegram.download(`${window.location.origin}/api${url}`, `zakaz-naryad-${visit.data?.plate_number ?? visitId}.pdf`),
  });

  return (
    <>
      <ScreenHeader title="Заезд" back />
      <Loadable query={visit} notFound="Заезд не найден" backTo="/visits">
        {(v) => (
          <div className="stack">
            <div className="row">
              <Plate value={v.plate_number} />
              <StatusTag kind="visit" status={v.status} />
            </div>
            <div className="visit-car">{v.make_model}</div>
            <Link className="hint" to={`/clients/${v.client_id}`}>{v.client_name} ›</Link>
            <span className="hint">{formatKm(v.mileage_at_intake)} · мастер {v.master_name}</span>
            <div className="total">
              <span className="hint">Итого по заезду</span>
              <b>{formatRub(v.total_amount)}</b>
            </div>
            <h2 className="section-title">Работы</h2>
            <Loadable query={lines}>
              {(l) =>
                l.works.length === 0 ? (
                  <EmptyState text="Работ пока нет" />
                ) : (
                  <>
                    <div className="card">
                      {l.works.map((w) => (
                        <div key={w.id} className="work-line">
                          <Link className="list-row" to={`/visits/${visitId}/works/${w.id}`}>
                            <span aria-hidden="true">{WORK_STATUS_ICONS[w.status]}</span>
                            <span>
                              <span className="block">{w.name}</span>
                              <span className="hint block">
                                {w.assigned_mechanic_name ?? 'без исполнителя'}
                                {w.approved_by_client ? '' : ' · не согласовано'}
                                {` · ${w.norm_hours} н/ч`}
                              </span>
                            </span>
                            <span className="mono">{formatRub(w.amount)}</span>
                          </Link>
                          {w.parts.map((p) => (
                            <div key={p.id} className="part-row hint">
                              <span>🔩 {p.name} × {p.quantity}</span>
                              <span className="mono">{formatRub(p.amount)}</span>
                            </div>
                          ))}
                        </div>
                      ))}
                    </div>
                    <p className="hint">Работы {formatRub(l.works_total)} · запчасти {formatRub(l.parts_total)}</p>
                  </>
                )
              }
            </Loadable>
            <div className="actions">
              <Link className="btn" to={`/visits/${visitId}/works/new`}>+ Работа</Link>
              <Button onClick={() => pdf.mutate()} busy={pdf.isPending}>PDF</Button>
              <Button variant="primary" className="span-2" disabled={v.allowed_next_statuses.length === 0} onClick={() => setStatusOpen(true)}>
                Сменить статус
              </Button>
            </div>
            <Sheet open={statusOpen} title="Сменить статус заезда" onClose={() => setStatusOpen(false)}>
              {v.allowed_next_statuses.map((s) => (
                <Button
                  key={s}
                  block
                  variant={s === 'cancelled' ? 'danger' : 'secondary'}
                  busy={changeStatus.isPending && changeStatus.variables === s}
                  disabled={changeStatus.isPending}
                  onClick={() => {
                    if (s === 'cancelled') {
                      setStatusOpen(false);
                      setCancelOpen(true);
                    } else {
                      changeStatus.mutate(s);
                    }
                  }}
                >
                  {VISIT_STATUS_LABELS[s]}
                </Button>
              ))}
            </Sheet>
            <CancelVisitSheet visitId={visitId} open={cancelOpen} onClose={() => setCancelOpen(false)} />
          </div>
        )}
      </Loadable>
    </>
  );
}
