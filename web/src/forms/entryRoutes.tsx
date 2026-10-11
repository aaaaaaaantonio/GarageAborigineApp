import { useNavigate, useSearchParams } from 'react-router-dom';
import { ScreenHeader } from '../ui/ScreenHeader';
import { ClientForm } from './ClientForm';
import { VehicleForm } from './VehicleForm';

export function NewClientRoute() {
  const navigate = useNavigate();
  return (
    <>
      <ScreenHeader title="Новый клиент" back />
      <ClientForm onCreated={(c) => navigate(`/clients/${c.id}`, { replace: true })} />
    </>
  );
}

export function NewVehicleRoute() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  return (
    <>
      <ScreenHeader title="Новый автомобиль" back />
      <VehicleForm clientId={params.get('client_id') ?? undefined} onCreated={(v) => navigate(`/vehicles/${v.id}`, { replace: true })} />
    </>
  );
}
