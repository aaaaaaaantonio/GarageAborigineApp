import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ApiError } from '../api/client';
import { clientsApi, searchApi, usersApi, vehiclesApi, visitsApi } from '../api/endpoints';
import type { Client, Vehicle } from '../api/types';
import { useAuth } from '../auth/AuthProvider';
import { formatKm } from '../lib/format';
import { useDebounced } from '../lib/useDebounced';
import { useGoBack } from '../lib/useGoBack';
import { ClientHit } from '../screens/hits';
import { telegram } from '../telegram/webapp';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';
import { Field } from '../ui/Field';
import { Loadable } from '../ui/Loadable';
import { Plate } from '../ui/Plate';
import { ScreenHeader } from '../ui/ScreenHeader';
import { useToast } from '../ui/Toast';
import { ClientForm } from './ClientForm';
import { VehicleForm } from './VehicleForm';

type Step = 'client' | 'client_new' | 'vehicle' | 'vehicle_new' | 'mileage' | 'master';

const STEP_TITLES: Record<Step, string> = {
  client: 'Шаг 1 · Клиент',
  client_new: 'Шаг 1 · Новый клиент',
  vehicle: 'Шаг 2 · Автомобиль',
  vehicle_new: 'Шаг 2 · Новый автомобиль',
  mileage: 'Шаг 3 · Пробег',
  master: 'Шаг 4 · Мастер',
};

const ROLLBACK_TEXT = 'Пробег меньше последнего зафиксированного. Подтвердите, если он верный, или исправьте.';

export function NewVisitWizard() {
  const { user } = useAuth();
  const isAdmin = user!.role === 'admin';
  const navigate = useNavigate();
  const goBack = useGoBack();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const presetVehicleId = params.get('vehicle_id');

  const [step, setStep] = useState<Step>('client');
  const [history, setHistory] = useState<Step[]>([]);
  const [clientQuery, setClientQuery] = useState('');
  const [client, setClient] = useState<Client | null>(null);
  const [vehicle, setVehicle] = useState<Vehicle | null>(null);
  const [mileage, setMileage] = useState('');
  const [mileageError, setMileageError] = useState('');
  const [rollback, setRollback] = useState(false);
  const [masterId, setMasterId] = useState<string | null>(null);
  const [ready, setReady] = useState(!presetVehicleId);

  useEffect(() => {
    if (!presetVehicleId) return;
    let cancelled = false;
    Promise.all([vehiclesApi.get(presetVehicleId), vehiclesApi.owner(presetVehicleId)])
      .then(([v, owner]) => {
        if (cancelled) return;
        if (owner) {
          setClient(owner);
          setVehicle(v);
          setStep('mileage');
        }
        setReady(true);
      })
      .catch(() => !cancelled && setReady(true));
    return () => {
      cancelled = true;
    };
  }, [presetVehicleId]);

  function go(next: Step, opts: { resetHistory?: boolean } = {}) {
    setHistory((h) => (opts.resetHistory ? [] : [...h, step]));
    setStep(next);
  }

  const dirty = client !== null || clientQuery.trim() !== '' || mileage !== '';

  useEffect(() => {
    if (!dirty) return;
    const onUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', onUnload);
    return () => window.removeEventListener('beforeunload', onUnload);
  }, [dirty]);

  function leave() {
    if (dirty && !window.confirm('Прервать новый заезд?')) return;
    goBack();
  }

  function back() {
    if (history.length === 0) {
      leave();
      return;
    }
    setStep(history[history.length - 1]);
    setHistory((h) => h.slice(0, -1));
    setRollback(false);
  }

  const creating = useRef(false);
  const backRef = useRef(back);
  backRef.current = back;
  useEffect(() => telegram.showBack(() => backRef.current()), []);

  const debouncedQuery = useDebounced(clientQuery.trim(), 300);
  const clientSearch = useQuery({
    queryKey: ['search', debouncedQuery],
    queryFn: () => searchApi.search(debouncedQuery),
    enabled: step === 'client' && debouncedQuery.length >= 2,
  });
  const clientVehicles = useQuery({
    queryKey: ['clientVehicles', client?.id],
    queryFn: () => clientsApi.vehicles(client!.id),
    enabled: step === 'vehicle' && client !== null,
  });
  const masters = useQuery({ queryKey: ['masters'], queryFn: usersApi.masters, enabled: step === 'master' });

  const create = useMutation({
    mutationFn: (vars: { confirmed: boolean; masterId: string }) =>
      visitsApi.create({
        client_id: client!.id,
        vehicle_id: vehicle!.id,
        assigned_master_id: vars.masterId,
        mileage_at_intake: Number(mileage.trim()),
        mileage_manually_confirmed: vars.confirmed,
      }),
    onSettled: () => {
      creating.current = false;
    },
    onSuccess: async (visit) => {
      telegram.haptic('success');
      await queryClient.invalidateQueries({ queryKey: ['visits'] });
      navigate(`/visits/${visit.id}`, { replace: true });
    },
    onError: (e) => {
      telegram.haptic('error');
      if (e instanceof ApiError && e.status === 409) {
        setRollback(true);
        if (step === 'master') {
          setHistory((h) => h.slice(0, -1));
          setStep('mileage');
        }
        return;
      }
      toast.show(e.message);
    },
  });

  // Ref lock: a double tap submits twice before React re-renders the button as disabled.
  function startCreate(vars: { confirmed: boolean; masterId: string }) {
    if (creating.current) return;
    creating.current = true;
    create.mutate(vars);
  }

  function submitMileage(e: FormEvent) {
    e.preventDefault();
    if (!/^\d+$/.test(mileage.trim())) {
      setMileageError('Введите число (пробег в км)');
      return;
    }
    setMileageError('');
    setRollback(false);
    if (isAdmin) {
      go('master');
      return;
    }
    startCreate({ confirmed: false, masterId: user!.id });
  }

  function pickMaster(id: string) {
    setMasterId(id);
    startCreate({ confirmed: false, masterId: id });
  }

  function confirmMileage() {
    startCreate({ confirmed: true, masterId: masterId ?? user!.id });
  }

  const clientHits = (clientSearch.data ?? []).filter((h) => h.entity === 'client');

  return (
    <>
      <ScreenHeader title="Новый заезд" back onBack={back} right={<Button variant="ghost" onClick={leave}>Отмена</Button>} />
      <p className="wizard-step">
        {STEP_TITLES[step]}
        {client && step !== 'client' && step !== 'client_new' ? ` · ${client.full_name}` : ''}
      </p>
      {!ready && <div className="loading">Загрузка…</div>}

      {ready && step === 'client' && (
        <div className="stack">
          <Field label="Телефон или ФИО клиента" value={clientQuery} onChange={(e) => setClientQuery(e.target.value)} autoComplete="off" autoFocus />
          {debouncedQuery.length >= 2 && clientSearch.isSuccess && clientHits.length === 0 && <EmptyState text="Клиент не найден" />}
          {clientHits.map((h) => (
            <ClientHit key={h.id} id={h.id} onPick={(c) => { setClient(c); go('vehicle'); }} />
          ))}
          <Button block onClick={() => go('client_new')}>+ Новый клиент</Button>
        </div>
      )}

      {step === 'client_new' && (
        <ClientForm
          initialQuery={clientQuery.trim()}
          submitLabel="Создать и продолжить"
          onCreated={(c) => {
            setClient(c);
            go('vehicle', { resetHistory: true });
          }}
        />
      )}

      {step === 'vehicle' && (
        <div className="stack">
          <Loadable query={clientVehicles}>
            {(list) =>
              list.length === 0 ? (
                <EmptyState text="У клиента нет машин" />
              ) : (
                <>
                  {list.map((v) => (
                    <button key={v.id} type="button" className="card card-link hit" onClick={() => { setVehicle(v); go('mileage'); }}>
                      <div className="row">
                        <Plate value={v.plate_number} />
                        <span>{v.make} {v.model}</span>
                      </div>
                    </button>
                  ))}
                </>
              )
            }
          </Loadable>
          <Button block onClick={() => go('vehicle_new')}>+ Новый автомобиль</Button>
        </div>
      )}

      {step === 'vehicle_new' && client && (
        <VehicleForm
          clientId={client.id}
          submitLabel="Создать и продолжить"
          onCreated={(v) => {
            setVehicle(v);
            go('mileage', { resetHistory: true });
          }}
        />
      )}

      {ready && step === 'mileage' && vehicle && (
        <form className="form" noValidate onSubmit={submitMileage}>
          <div className="row">
            <Plate value={vehicle.plate_number} />
            <span>{vehicle.make} {vehicle.model}</span>
          </div>
          <p className="hint">Последний пробег: {formatKm(vehicle.mileage_current)}</p>
          <Field label="Пробег на приёмке, км" inputMode="numeric" value={mileage} onChange={(e) => setMileage(e.target.value)} error={mileageError} autoFocus />
          {rollback && (
            <>
              <p className="form-error" role="alert">{ROLLBACK_TEXT}</p>
              <Button variant="secondary" block busy={create.isPending} onClick={confirmMileage}>Подтвердить пробег</Button>
            </>
          )}
          <Button type="submit" variant="primary" block busy={create.isPending}>{isAdmin ? 'Далее' : 'Создать заезд'}</Button>
        </form>
      )}

      {step === 'master' && (
        <div className="stack">
          <Loadable query={masters}>
            {(list) =>
              list.length === 0 ? (
                <EmptyState text="Сначала добавьте мастера в «Ещё → Добавить сотрудника»" />
              ) : (
                <>
                  {list.map((m) => (
                    <Button key={m.id} block busy={create.isPending && create.variables?.masterId === m.id} disabled={create.isPending} onClick={() => pickMaster(m.id)}>
                      {m.full_name}
                    </Button>
                  ))}
                </>
              )
            }
          </Loadable>
        </div>
      )}
    </>
  );
}
