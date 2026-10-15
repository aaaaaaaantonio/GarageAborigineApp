import type { StatsChartData } from '../../api/types';
import { BarChart } from './BarChart';
import { HBarChart } from './HBarChart';
import { ShareMeter } from './ShareMeter';
import { StackedBarChart } from './StackedBarChart';

function Body({ chart }: { chart: StatsChartData }) {
  const [first] = chart.series;
  switch (chart.kind) {
    case 'stack': return <StackedBarChart title={chart.title} labels={chart.labels} series={chart.series} unit={chart.unit} />;
    case 'hbars': return <HBarChart title={chart.title} labels={chart.labels} values={first.values} unit={chart.unit} />;
    case 'share': return <ShareMeter title={chart.title} labels={chart.labels} values={first.values} />;
    default: return <BarChart title={chart.title} labels={chart.labels} values={first.values} unit={chart.unit} />;
  }
}

export function StatsChart({ chart }: { chart: StatsChartData }) {
  const empty = chart.labels.length === 0 || chart.series.every((s) => s.values.every((v) => v === 0));
  return (
    <section className="card chart">
      <h2>{chart.title}</h2>
      {chart.sub && <span className="hint">{chart.sub}</span>}
      {empty ? <p className="hint chart-empty">Нет данных за период</p> : <Body key={chart.labels.join('|')} chart={chart} />}
    </section>
  );
}
