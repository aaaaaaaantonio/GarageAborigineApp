import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { clientsApi, visitsApi } from '../api/endpoints';
import { Card } from '../ui/Card';
import { EmptyState } from '../ui/EmptyState';
import { Loadable } from '../ui/Loadable';
import { Plate } from '../ui/Plate';
import { ScreenHeader } from '../ui/ScreenHeader';
import { VisitHistory } from './VisitHistory';

export function ClientScreen() {
  const { clientId = '' } = useParams();
  const client = useQuery({ queryKey: ['client', clientId], queryFn: () => clientsApi.get(clientId) });
  const vehicles = useQuery({ queryKey: ['clientVehicles', clientId], queryFn: () => clientsApi.vehicles(clientId) });
  const visits = useQuery({ queryKey: ['visitsFor', 'client', clientId], queryFn: () => visitsApi.listForClient(clientId) });
  return (
    <>
      <ScreenHeader title="Клиент" back />
      <Loadable query={client} notFound="Клиент не найден">
        {(c) => (
          <div className="stack">
            <div className="card">
              <b className="title">{c.full_name}</b>
              <a className="hint" href={`tel:${c.phone_display.replace(/[^\d+]/g, '')}`}>{c.phone_display}</a>
            </div>
            <h2 className="section-title">Автомобили</h2>
            <Loadable query={vehicles}>
              {(list) =>
                list.length === 0 ? (
                  <EmptyState text="Машин нет" />
                ) : (
                  <div className="stack">
                    {list.map((v) => (
                      <Card key={v.id} to={`/vehicles/${v.id}`}>
                        <div className="row">
                          <Plate value={v.plate_number} />
                          <span>{v.make} {v.model}</span>
                        </div>
                      </Card>
                    ))}
                  </div>
                )
              }
            </Loadable>
            <Link className="btn btn-block" to={`/vehicles/new?client_id=${clientId}`}>+ Автомобиль</Link>
            <h2 className="section-title">Заезды</h2>
            <Loadable query={visits}>{(d) => <VisitHistory visits={d.items} />}</Loadable>
          </div>
        )}
      </Loadable>
    </>
  );
}
