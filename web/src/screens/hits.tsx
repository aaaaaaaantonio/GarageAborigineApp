import { useQuery } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { clientsApi, vehiclesApi } from '../api/endpoints';
import type { Client, Vehicle } from '../api/types';
import { Card } from '../ui/Card';
import { Plate } from '../ui/Plate';

function Hit({ to, onPick, children }: { to: string; onPick?: () => void; children: ReactNode }) {
  if (onPick) {
    return <button type="button" className="card card-link hit" onClick={onPick}>{children}</button>;
  }
  return <Card to={to}>{children}</Card>;
}

export function ClientHit({ id, onPick }: { id: string; onPick?: (c: Client) => void }) {
  const q = useQuery({ queryKey: ['client', id], queryFn: () => clientsApi.get(id) });
  if (!q.data) return null;
  const client = q.data;
  return (
    <Hit to={`/clients/${id}`} onPick={onPick && (() => onPick(client))}>
      <b>{client.full_name}</b>
      <span className="hint">{client.phone_display}</span>
    </Hit>
  );
}

export function VehicleHit({ id, onPick }: { id: string; onPick?: (v: Vehicle) => void }) {
  const q = useQuery({ queryKey: ['vehicle', id], queryFn: () => vehiclesApi.get(id) });
  if (!q.data) return null;
  const vehicle = q.data;
  return (
    <Hit to={`/vehicles/${id}`} onPick={onPick && (() => onPick(vehicle))}>
      <div className="row">
        <Plate value={vehicle.plate_number} />
        <span>{vehicle.make} {vehicle.model}</span>
      </div>
      {vehicle.vin && <span className="hint mono">{vehicle.vin}</span>}
    </Hit>
  );
}

export function HitList({ hits }: { hits: { entity: 'client' | 'vehicle'; id: string }[] }) {
  return (
    <div className="stack">
      {hits.map((h) =>
        h.entity === 'client' ? <ClientHit key={`c-${h.id}`} id={h.id} /> : <VehicleHit key={`v-${h.id}`} id={h.id} />,
      )}
    </div>
  );
}
