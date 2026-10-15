import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { visitsApi } from '../api/endpoints';
import type { MechanicWork } from '../api/types';
import { formatHours, formatKm, formatRub } from '../lib/format';
import { Loadable } from '../ui/Loadable';
import { Plate } from '../ui/Plate';
import { ScreenHeader } from '../ui/ScreenHeader';
import { StatusTag } from '../ui/StatusTag';

const NO_SCHEME = 'схема оплаты не задана';

export function payText(pay: number | null): string {
  return pay === null ? NO_SCHEME : formatRub(pay);
}

export function MechanicVisitScreen() {
  const { visitId = '' } = useParams();
  const query = useQuery({ queryKey: ['mechanicVisit', visitId], queryFn: () => visitsApi.mechanicView(visitId) });
  return (
    <>
      <ScreenHeader title="Заезд" back />
      <Loadable query={query}>
        {(v) => {
          const prices = v.total_amount !== null;
          return (
            <div className="stack">
              <div className="card">
                <div className="row">
                  <Plate value={v.plate_number} />
                  <StatusTag kind="visit" status={v.status} />
                </div>
                <span>{v.make_model}</span>
                <span className="hint">Пробег: {formatKm(v.mileage_at_intake)} · Мастер: {v.master_name}</span>
                {v.client_name && <span className="hint">Клиент: {v.client_name}</span>}
                {v.client_phone && <span className="hint">Телефон: {v.client_phone}</span>}
                {v.client_telegram_username && <TelegramLine username={v.client_telegram_username} />}
                {v.vin && <span className="hint mono">VIN: {v.vin}</span>}
              </div>
              <h2 className="section-title">Работы</h2>
              {v.works.map((w) => <WorkCard key={w.id} w={w} prices={prices} />)}
              {prices && (
                <div className="card">
                  {v.discount ? (
                    <div className="row"><span>Скидка</span><span className="mono">−{formatRub(v.discount)}</span></div>
                  ) : null}
                  <div className="row"><b>Итого по заезду</b><b className="mono">{formatRub(v.total_amount!)}</b></div>
                  <div className="row"><span>Ваш заработок по заезду</span><span className="mono">{payText(v.my_pay_total)}</span></div>
                </div>
              )}
            </div>
          );
        }}
      </Loadable>
    </>
  );
}

function TelegramLine({ username }: { username: string }) {
  const name = username.replace(/^@/, '');
  return <span className="hint">Telegram: <a href={`https://t.me/${name}`}>@{name}</a></span>;
}

function WorkCard({ w, prices }: { w: MechanicWork; prices: boolean }) {
  return (
    <div className="card">
      <div className="row">
        <b>{w.is_mine ? `${w.name} · моя` : w.name}</b>
        <StatusTag kind="work" status={w.status} />
      </div>
      <span className="hint">{w.mechanic_name ?? 'без исполнителя'} · {formatHours(w.norm_hours)}</span>
      {prices && w.amount !== null && (
        <div className="row"><span className="hint">Стоимость</span><span className="mono">{formatRub(w.amount)}</span></div>
      )}
      {prices && w.is_mine && (
        <div className="row"><span>Ваш заработок</span><span className="mono">{payText(w.my_pay)}</span></div>
      )}
      {w.parts.map((p, i) => (
        <div key={i} className="part-row hint">
          <span>🔩 {p.name} × {p.quantity}</span>
          {p.amount !== null && <span className="mono">{formatRub(p.amount)}</span>}
        </div>
      ))}
    </div>
  );
}
