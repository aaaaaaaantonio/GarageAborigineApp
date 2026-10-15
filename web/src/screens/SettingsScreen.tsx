import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { settingsApi } from '../api/endpoints';
import type { MechanicPay, PayScheme, VisibilitySettings } from '../api/types';
import { parseNumber } from '../lib/format';
import { useAction } from '../lib/useAction';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';
import { Field } from '../ui/Field';
import { Loadable } from '../ui/Loadable';
import { Picker } from '../ui/Picker';
import { ScreenHeader } from '../ui/ScreenHeader';
import { useToast } from '../ui/Toast';

const TOGGLES: [keyof VisibilitySettings, string][] = [
  ['mechanic_sees_prices', 'Цены и заработок'],
  ['mechanic_sees_client_name', 'Имя клиента'],
  ['mechanic_sees_client_phone', 'Телефон клиента'],
  ['mechanic_sees_vin', 'VIN / номер кузова'],
];

type SchemeChoice = PayScheme | 'none';
const SCHEMES: { value: SchemeChoice; label: string }[] = [
  { value: 'none', label: 'Не задана' },
  { value: 'percent', label: 'Процент от работы' },
  { value: 'per_hour', label: 'Фикс за нормо-час' },
  { value: 'full', label: 'Вся стоимость' },
];

export function SettingsScreen() {
  const toast = useToast();
  const settings = useQuery({ queryKey: ['settings'], queryFn: settingsApi.get });
  const pay = useQuery({ queryKey: ['mechanicPay'], queryFn: settingsApi.pay });
  const toggle = useAction((patch: Partial<VisibilitySettings>) => settingsApi.update(patch), {
    invalidate: [['settings']],
    onSuccess: () => toast.show('Сохранено'),
  });
  return (
    <>
      <ScreenHeader title="Настройки" back />
      <div className="stack">
        <h2 className="section-title">Что видят механики</h2>
        <Loadable query={settings}>
          {(s) => (
            <div className="card">
              {TOGGLES.map(([key, label]) => (
                <label key={key} className="toggle-row">
                  <span>{label}</span>
                  <input type="checkbox" role="switch" checked={s[key]} disabled={toggle.isPending}
                    onChange={(e) => toggle.mutate({ [key]: e.target.checked })} />
                </label>
              ))}
            </div>
          )}
        </Loadable>
        <h2 className="section-title">Оплата механиков</h2>
        <Loadable query={pay}>
          {(list) => list.length === 0
            ? <EmptyState text="Механиков нет" />
            : <>{list.map((m) => <PayRow key={m.user_id} m={m} />)}</>}
        </Loadable>
      </div>
    </>
  );
}

function PayRow({ m }: { m: MechanicPay }) {
  const toast = useToast();
  const [scheme, setScheme] = useState<SchemeChoice>(m.pay_scheme ?? 'none');
  const [value, setValue] = useState(m.pay_value === null ? '' : String(m.pay_value).replace('.', ','));
  const needsValue = scheme === 'percent' || scheme === 'per_hour';
  const save = useAction(
    () => settingsApi.setPay(m.user_id, scheme === 'none' ? null : scheme, needsValue ? parseNumber(value) : null),
    { invalidate: [['mechanicPay']], onSuccess: () => toast.show('Сохранено') },
  );
  return (
    <div className="card">
      <b>{m.full_name}</b>
      <Picker label="Схема оплаты" value={scheme} options={SCHEMES} onChange={setScheme} />
      {needsValue && (
        <Field label={scheme === 'percent' ? 'Процент, %' : 'Ставка, ₽ за н/ч'} inputMode="decimal"
          value={value} onChange={(e) => setValue(e.target.value)} />
      )}
      <Button block busy={save.isPending} onClick={() => save.mutate()}>Сохранить</Button>
    </div>
  );
}
