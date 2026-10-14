import type { StatsUnit } from '../../api/types';
import { formatValue } from './format';

const W = 400, ROW = 34, VALUE_ROOM = 96;

/** Ranked rows: label above each bar, value at its end — reads well at phone width. */
export function HBarChart({ title, labels, values, unit }: { title: string; labels: string[]; values: number[]; unit: StatsUnit }) {
  const max = Math.max(...values);
  return (
    <svg viewBox={`0 0 ${W} ${labels.length * ROW}`} role="img" aria-label={title}>
      {labels.map((label, i) => {
        const y0 = i * ROW;
        const w = Math.max(4, (values[i] / max) * (W - VALUE_ROOM));
        const r = Math.min(4, w);
        return (
          <g key={label}>
            <text x={0} y={y0 + 11} className="chart-label">{label}</text>
            <path d={`M0,${y0 + 16} H${w - r} Q${w},${y0 + 16} ${w},${y0 + 16 + r} V${y0 + 30 - r} Q${w},${y0 + 30} ${w - r},${y0 + 30} H0 Z`}
              fill="var(--series-1)" />
            <text x={w + 8} y={y0 + 27} className="chart-value">{formatValue(values[i], unit)}</text>
          </g>
        );
      })}
    </svg>
  );
}
