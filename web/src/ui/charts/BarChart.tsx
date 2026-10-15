import { useState } from 'react';
import type { StatsUnit } from '../../api/types';
import { axisMax, describe, formatTick, formatValue } from './format';

export const W = 400;
export const H = 170;
const L = 38, R = 6, T = 14, B = 22;

/** Bar path with the data end (top) rounded and the baseline end square. */
export function roundedTop(x: number, top: number, w: number, h: number): string {
  const r = Math.min(4, h, w / 2);
  return `M${x},${top + h} V${top + r} Q${x},${top} ${x + r},${top} H${x + w - r} Q${x + w},${top} ${x + w},${top + r} V${top + h} Z`;
}

export interface Frame { y: (v: number) => number; ticks: number[]; step: number; barW: number; x: (i: number) => number; every: number; base: number }

const CHAR_W = 6.2;

/** Shared geometry for vertical bar charts over `n` steps with axis top `max`. */
export function frame(n: number, max: number, labels: string[] = []): Frame {
  const step = (W - L - R) / n;
  const barW = Math.min(46, step * 0.6);
  return {
    y: (v) => H - B - (v / max) * (H - B - T),
    ticks: [0, 1, 2, 3].map((i) => (max * i) / 3),
    step, barW,
    x: (i) => L + step * i + (step - barW) / 2,
    every: Math.max(1, Math.ceil((Math.max(0, ...labels.map((l) => l.length)) * CHAR_W + 4) / step)),
    base: H - B,
  };
}

export function Axis({ f, unit, labels }: { f: Frame; unit: StatsUnit; labels: string[] }) {
  return (
    <>
      {f.ticks.map((t) => (
        <g key={t}>
          <line x1={L} x2={W - R} y1={f.y(t)} y2={f.y(t)} className="chart-grid" />
          <text x={L - 6} y={f.y(t) + 4} textAnchor="end">{formatTick(t, unit)}</text>
        </g>
      ))}
      {labels.map((label, i) => (labels.length - 1 - i) % f.every === 0 && (
        <text key={i} x={f.x(i) + f.barW / 2} y={H - 6} textAnchor="middle">{label}</text>
      ))}
    </>
  );
}

/** Amber frame around the tapped bar, with a small gap so the bar's own colours stay visible. */
export function ActiveOutline({ f, i, top }: { f: Frame; i: number; top: number }) {
  const gap = 2.5;
  return (
    <rect data-testid="bar-outline" data-bar={i} className="chart-outline" x={f.x(i) - gap} y={top - gap}
      width={f.barW + 2 * gap} height={f.base - top + gap} rx={5} />
  );
}

export const DIMMED = 0.6;

export function HitAreas({ f, n, onPick }: { f: Frame; n: number; onPick: (i: number) => void }) {
  return (
    <>
      {Array.from({ length: n }, (_, i) => (
        <rect key={i} data-testid={`bar-${i}`} className="chart-hit" x={L + f.step * i} y={T} width={f.step} height={f.base - T}
          onPointerEnter={() => onPick(i)} onClick={() => onPick(i)} />
      ))}
    </>
  );
}

export function BarChart({ title, labels, values, unit }: { title: string; labels: string[]; values: number[]; unit: StatsUnit }) {
  const [active, setActive] = useState(labels.length - 1);
  const shown = Math.min(active, labels.length - 1);
  const f = frame(labels.length, axisMax(Math.max(...values), unit), labels);
  return (
    <>
      <div className="chart-readout" data-testid="readout">{labels[shown]} · <b>{formatValue(values[shown], unit)}</b></div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={describe(title, labels, (i) => formatValue(values[i], unit))}>
        <Axis f={f} unit={unit} labels={labels} />
        {values.map((v, i) => v > 0 && (
          <path key={i} d={roundedTop(f.x(i), f.y(v), f.barW, f.base - f.y(v))} fill="var(--series-1)"
            opacity={i === shown ? 1 : DIMMED} />
        ))}
        {values[shown] > 0 && <ActiveOutline f={f} i={shown} top={f.y(values[shown])} />}
        <HitAreas f={f} n={labels.length} onPick={setActive} />
      </svg>
    </>
  );
}
