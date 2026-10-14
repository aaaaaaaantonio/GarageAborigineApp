import type { StatsKpi } from '../../api/types';
import { formatValue } from './format';

function Delta({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="kpi-delta">— к прошлому периоду</span>;
  if (pct === 0) return <span className="kpi-delta">= как в прошлом периоде</span>;
  return <span className={`kpi-delta ${pct > 0 ? 'up' : 'down'}`}>{`${pct > 0 ? '▲' : '▼'} ${Math.abs(pct)}% к прошлому периоду`}</span>;
}

export function KpiTile({ kpi }: { kpi: StatsKpi }) {
  return (
    <div className="kpi">
      <span className="hint">{kpi.label}</span>
      <span className="kpi-value mono">{formatValue(kpi.value, kpi.unit)}</span>
      {kpi.compare && <Delta pct={kpi.delta_pct} />}
    </div>
  );
}
