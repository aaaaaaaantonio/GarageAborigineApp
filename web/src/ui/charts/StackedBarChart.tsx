import { useState } from 'react';
import type { StatsUnit } from '../../api/types';
import { Axis, H, HitAreas, W, frame, roundedTop } from './BarChart';
import { axisMax, describe, formatValue } from './format';

const COLORS = ['var(--series-1)', 'var(--series-2)'];

export function StackedBarChart({ title, labels, series, unit }: {
  title: string; labels: string[]; series: { name: string; values: number[] }[]; unit: StatsUnit;
}) {
  const [active, setActive] = useState(labels.length - 1);
  const shown = Math.min(active, labels.length - 1);
  const [bottom, top] = series;
  const totals = labels.map((_, i) => bottom.values[i] + top.values[i]);
  const f = frame(labels.length, axisMax(Math.max(...totals), unit), labels);
  return (
    <>
      <div className="legend">
        {series.map((s, i) => <span key={s.name}><i style={{ background: COLORS[i] }} />{s.name}</span>)}
      </div>
      <div className="chart-readout" data-testid="readout">
        {labels[shown]}{series.map((s) => ` · ${s.name} ${formatValue(s.values[shown], unit)}`).join('')}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={describe(title, labels, (i) => series.map((s) => `${s.name} ${formatValue(s.values[i], unit)}`).join(', '))}>
        <Axis f={f} unit={unit} labels={labels} />
        {labels.map((_, i) => {
          const a = bottom.values[i], b = top.values[i];
          const ya = f.y(a), yb = f.y(a + b);
          return (
            <g key={i} opacity={i === shown ? 1 : 0.75}>
              {a > 0 && (b > 0
                ? <rect x={f.x(i)} y={ya} width={f.barW} height={f.base - ya} fill={COLORS[0]} />
                : <path d={roundedTop(f.x(i), ya, f.barW, f.base - ya)} fill={COLORS[0]} />)}
              {b > 0 && <path d={roundedTop(f.x(i), yb, f.barW, Math.max(0, ya - yb - (a > 0 ? 2 : 0)))} fill={COLORS[1]} />}
            </g>
          );
        })}
        <HitAreas f={f} n={labels.length} onPick={setActive} />
      </svg>
    </>
  );
}
