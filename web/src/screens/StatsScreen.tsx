import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { statsApi, usersApi } from '../api/endpoints';
import type { StatsPeriod, StatsSection } from '../api/types';
import { useAuth } from '../auth/AuthProvider';
import { KpiTile } from '../ui/charts/KpiTile';
import { StatsChart } from '../ui/charts/StatsChart';
import { Loadable } from '../ui/Loadable';
import { Picker } from '../ui/Picker';
import { ScreenHeader } from '../ui/ScreenHeader';

const PERIODS: { value: StatsPeriod; label: string }[] = [
  { value: 'week', label: 'Неделя' },
  { value: 'month', label: 'Месяц' },
  { value: 'quarter', label: 'Квартал' },
  { value: 'year', label: 'Год' },
];
const SECTIONS: { value: StatsSection; label: string }[] = [
  { value: 'money', label: 'Деньги' },
  { value: 'flow', label: 'Поток' },
  { value: 'staff', label: 'Сотрудники' },
  { value: 'works', label: 'Работы и клиенты' },
];

export function StatsScreen() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [section, setSection] = useState<StatsSection>('money');
  const [period, setPeriod] = useState<StatsPeriod>('month');
  const [masterId, setMasterId] = useState('');
  const masters = useQuery({ queryKey: ['masters'], queryFn: usersApi.masters, enabled: isAdmin });
  const query = useQuery({
    queryKey: ['stats', user?.id, isAdmin ? section : 'mine', period, masterId],
    queryFn: () => (isAdmin ? statsApi.section(section, period, masterId || undefined) : statsApi.mine(period)),
    placeholderData: keepPreviousData,
  });
  return (
    <>
      {/* Mechanics open it from the tab bar; admins and masters from «Ещё». */}
      <ScreenHeader title="Статистика" back={user?.role !== 'mechanic'} />
      {isAdmin && (
        <div className="seg" role="tablist" aria-label="Раздел">
          {SECTIONS.map((s) => (
            <button key={s.value} type="button" role="tab" aria-selected={s.value === section} onClick={() => setSection(s.value)}>
              {s.label}
            </button>
          ))}
        </div>
      )}
      <div className="filters-row">
        <Picker label="Период" value={period} options={PERIODS} onChange={setPeriod} />
        {isAdmin && (
          <Picker label="Мастер" value={masterId} onChange={setMasterId}
            options={[{ value: '', label: 'Все мастера' }, ...(masters.data ?? []).map((m) => ({ value: m.id, label: m.full_name }))]} />
        )}
      </div>
      <Loadable query={query}>
        {(stats) => (
          <div className="stack">
            <div className="kpis">{stats.kpis.map((k) => <KpiTile key={k.key} kpi={k} />)}</div>
            {stats.charts.map((c) => <StatsChart key={`${stats.period}-${c.key}`} chart={c} />)}
          </div>
        )}
      </Loadable>
    </>
  );
}
