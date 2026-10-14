const COLORS = ['var(--series-1)', 'var(--series-2)'];

export function ShareMeter({ labels, values }: { labels: string[]; values: number[] }) {
  const total = values.reduce((a, b) => a + b, 0);
  const pct = (v: number) => Math.round((v / total) * 100);
  return (
    <div className="meter">
      <div className="meter-bar">
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
