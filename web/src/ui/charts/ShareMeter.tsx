const COLORS = ['var(--series-1)', 'var(--series-2)'];

import { describe } from './format';

export function ShareMeter({ title, labels, values }: { title: string; labels: string[]; values: number[] }) {
  const total = values.reduce((a, b) => a + b, 0);
  const pct = (v: number) => Math.round((v / total) * 100);
  return (
    <div className="meter">
      <div className="meter-bar" role="img" aria-label={describe(title, labels, (i) => `${values[i]} (${pct(values[i])} %)`)}>
        {values.map((v, i) => v > 0 && <span key={labels[i]} style={{ width: `${pct(v)}%`, background: COLORS[i] }} />)}
      </div>
      <div className="row">
        {labels.map((label, i) => (
          <span key={label} className="hint"><i className="swatch" style={{ background: COLORS[i] }} />{`${label}: ${values[i]} (${pct(values[i])} %)`}</span>
        ))}
      </div>
    </div>
  );
}
