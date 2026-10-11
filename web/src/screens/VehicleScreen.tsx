import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { vehiclesApi, visitsApi } from '../api/endpoints';
import { useAuth } from '../auth/AuthProvider';
import { formatDate, formatKm } from '../lib/format';
import { WORK_STATUS_ICONS } from '../lib/labels';
import { Card } from '../ui/Card';
import { EmptyState } from '../ui/EmptyState';
import { Loadable } from '../ui/Loadable';
import { Plate } from '../ui/Plate';
import { ScreenHeader } from '../ui/ScreenHeader';
import { VisitHistory } from './VisitHistory';

export function VehicleScreen() {
  const { vehicleId = '' } = useParams();
  const { user } = useAuth();
  const isStaff = user!.role !== 'mechanic';
  const vehicle = useQuery({ queryKey: ['vehicle', vehicleId], queryFn: () => vehiclesApi.get(vehicleId) });
  const owner = useQuery({ queryKey: ['vehicleOwner', vehicleId], queryFn: () => vehiclesApi.owner(vehicleId), enabled: isStaff });
  const visits = useQuery({ queryKey: ['visitsFor', 'vehicle', vehicleId], queryFn: () => visitsApi.listForVehicle(vehicleId), enabled: isStaff });
  const history = useQuery({ queryKey: ['workHistory', vehicleId], queryFn: () => vehiclesApi.workHistory(vehicleId) });
  return (
    <>
      <ScreenHeader title="Машина" back />
      <Loadable query={vehicle} notFound="Машина не найдена">
        {(v) => (
          <div className="stack">
            <div className="card">
              <Plate value={v.plate_number} />
              <b className="title">{v.make} {v.model}</b>
              <span className="hint mono">VIN {v.vin}</span>
              <span className="hint">Пробег {formatKm(v.mileage_current)}</span>
            </div>
            {isStaff && (
              <>
                <Loadable query={owner}>
                  {(o) =>
                    o ? (
                      <Card to={`/clients/${o.id}`}>
                        <span className="hint">Владелец</span>
                        <b>{o.full_name}</b>
                      </Card>
                    ) : (
                      <EmptyState text="Владелец не указан" />
                    )
                  }
                </Loadable>
                <Link className="btn btn-primary btn-block" to={`/visits/new?vehicle_id=${v.id}`}>+ Новый заезд</Link>
                <h2 className="section-title">Заезды</h2>
                <Loadable query={visits}>{(d) => <VisitHistory visits={d.items} />}</Loadable>
              </>
            )}
            <h2 className="section-title">История работ</h2>
            <Loadable query={history}>
              {(h) =>
                h.items.length === 0 ? (
                  <EmptyState text="Работ по машине ещё не было" />
                ) : (
                  <div className="card">
                    {h.items.map((w, i) => (
                      <div key={`${w.visit_id}-${i}`} className="list-row">
                        <span aria-hidden="true">{WORK_STATUS_ICONS[w.status]}</span>
                        <span>
                          <span className="block">{w.name}</span>
                          <span className="hint block">{formatDate(w.visit_at)} · {formatKm(w.mileage)}</span>
                        </span>
                        <span />
                      </div>
                    ))}
                  </div>
                )
              }
            </Loadable>
          </div>
        )}
      </Loadable>
    </>
  );
}
