import { BarChart } from './BarChart';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { StatsChartData, StatsKpi } from '../../api/types';
import { formatValue, niceMax } from './format';
import { KpiTile } from './KpiTile';
import { StatsChart } from './StatsChart';

const LABELS = ['15.09–16.09', '17.09–23.09', '24.09–30.09', '01.10–07.10', '08.10–14.10'];
const chart = (over: Partial<StatsChartData>): StatsChartData => ({
  key: 'k', kind: 'bars', title: 'Выручка', sub: null, unit: 'rub', labels: LABELS,
  series: [{ name: 'Выручка', values: [0, 6000, 0, 0, 14000] }], ...over,
});

test('formats values by unit', () => {
  expect(formatValue(14000, 'rub')).toBe('14 000 ₽');
  expect(formatValue(7.5, 'hours')).toBe('7,5 н/ч');
  expect(formatValue(0.5, 'days')).toBe('0,5 дн.');
  expect(formatValue(50, 'pct')).toBe('50 %');
  expect(formatValue('Toyota', 'text')).toBe('Toyota');
  expect(niceMax(14000)).toBe(15000);
  expect(niceMax(0)).toBe(1);
});

test('bar chart: axis top is the nice max, readout follows the tapped bar', async () => {
  render(<StatsChart chart={chart({})} />);
  expect(screen.getByRole('img', { name: /^Выручка/ })).toBeInTheDocument();
  expect(screen.getByText('15 т')).toBeInTheDocument();
  expect(screen.getByTestId('readout')).toHaveTextContent('08.10–14.10 · 14 000 ₽');
  await userEvent.click(screen.getByTestId('bar-1'));
  expect(screen.getByTestId('readout')).toHaveTextContent('17.09–23.09 · 6 000 ₽');
});

test('bar chart outlines the tapped bar, and only that one', async () => {
  render(<StatsChart chart={chart({})} />);
  expect(screen.getAllByTestId('bar-outline')).toHaveLength(1);
  expect(screen.getByTestId('bar-outline')).toHaveAttribute('data-bar', '4');
  await userEvent.click(screen.getByTestId('bar-1'));
  expect(screen.getAllByTestId('bar-outline')).toHaveLength(1);
  expect(screen.getByTestId('bar-outline')).toHaveAttribute('data-bar', '1');
  await userEvent.click(screen.getByTestId('bar-0'));
  expect(screen.queryByTestId('bar-outline')).toBeNull(); // empty bucket: nothing to outline
});

test('stacked chart outlines the whole tapped stack', async () => {
  render(<StatsChart chart={chart({ kind: 'stack', series: [
    { name: 'Работы', values: [0, 6000, 0, 0, 7000] }, { name: 'Запчасти', values: [0, 0, 0, 0, 7000] },
  ] })} />);
  expect(screen.getByTestId('bar-outline')).toHaveAttribute('data-bar', '4');
  await userEvent.click(screen.getByTestId('bar-1'));
  expect(screen.getByTestId('bar-outline')).toHaveAttribute('data-bar', '1');
});

test('stacked chart has a legend and per-series readout', () => {
  render(<StatsChart chart={chart({ kind: 'stack', series: [
    { name: 'Работы', values: [0, 6000, 0, 0, 7000] }, { name: 'Запчасти', values: [0, 0, 0, 0, 7000] },
  ] })} />);
  expect(screen.getByText('Работы')).toBeInTheDocument();
  expect(screen.getByTestId('readout')).toHaveTextContent('08.10–14.10 · Работы 7 000 ₽ · Запчасти 7 000 ₽');
});

test('horizontal bars show the value of each row', () => {
  render(<StatsChart chart={chart({ kind: 'hbars', unit: 'hours', title: 'Нормо-часы', labels: ['Морозов', 'Соколов'],
    series: [{ name: 'Нормо-часы', values: [6, 3] }] })} />);
  expect(screen.getByText('Морозов')).toBeInTheDocument();
  expect(screen.getByText('6 н/ч')).toBeInTheDocument();
});

test('share meter shows parts with percent', () => {
  render(<StatsChart chart={chart({ kind: 'share', unit: 'count', title: 'Клиенты', labels: ['Новые', 'Повторные'],
    series: [{ name: 'Клиенты', values: [1, 3] }] })} />);
  expect(screen.getByText('Новые: 1 (25 %)')).toBeInTheDocument();
});

test('a chart of zeros says there is no data', () => {
  render(<StatsChart chart={chart({ series: [{ name: 'Выручка', values: [0, 0, 0, 0, 0] }] })} />);
  expect(screen.getByText('Нет данных за период')).toBeInTheDocument();
  expect(screen.queryByRole('img')).not.toBeInTheDocument();
});

test('kpi tile shows delta or a dash', () => {
  const kpi: StatsKpi = { key: 'r', label: 'Выручка', value: 20000, unit: 'rub', delta_pct: 150, compare: true };
  const { rerender } = render(<KpiTile kpi={kpi} />);
  expect(screen.getByText('20 000 ₽')).toBeInTheDocument();
  expect(screen.getByText('▲ 150% к прошлому периоду')).toBeInTheDocument();
  rerender(<KpiTile kpi={{ ...kpi, delta_pct: null }} />);
  expect(screen.getByText('— к прошлому периоду')).toBeInTheDocument();
  rerender(<KpiTile kpi={{ ...kpi, compare: false }} />);
  expect(screen.queryByText(/к прошлому периоду/)).not.toBeInTheDocument();
});

test('readout clamps when the same chart gets fewer labels', () => {
  const { rerender } = render(<BarChart title="Т" labels={LABELS} values={[1, 2, 3, 4, 5]} unit="count" />);
  rerender(<BarChart title="Т" labels={['a', 'b']} values={[1, 2]} unit="count" />);
  expect(screen.getByTestId('readout')).toHaveTextContent('b · 2');
  expect(screen.getByTestId('readout')).not.toHaveTextContent('undefined');
});

test('count charts have whole-number ticks', () => {
  render(<StatsChart chart={chart({ unit: 'count', series: [{ name: 'Заезды', values: [0, 5, 0, 0, 2] }] })} />);
  expect(screen.getByText('4')).toBeInTheDocument();
  expect(screen.getByText('6')).toBeInTheDocument();
  expect(screen.queryByText(/,/)).not.toBeInTheDocument();
});

test('share meter is an image named with its title', () => {
  render(<StatsChart chart={chart({ kind: 'share', unit: 'count', title: 'Клиенты', labels: ['Новые', 'Повторные'],
    series: [{ name: 'Клиенты', values: [1, 3] }] })} />);
  expect(screen.getByRole('img', { name: /^Клиенты/ })).toBeInTheDocument();
});

test('chart aria-label carries the data', () => {
  render(<StatsChart chart={chart({})} />);
  expect(screen.getByRole('img').getAttribute('aria-label')).toContain('17.09–23.09 — 6 000 ₽');
});

test('readout shows the last bucket when the chart gets more labels', () => {
  const few = chart({ labels: ['янв', 'фев'], series: [{ name: 'Выручка', values: [1, 2] }] });
  const many = chart({ labels: Array.from({ length: 13 }, (_, i) => `м${i}`), series: [{ name: 'Выручка', values: Array.from({ length: 13 }, (_, i) => i + 1) }] });
  const { rerender } = render(<StatsChart chart={few} />);
  rerender(<StatsChart chart={many} />);
  expect(screen.getByTestId('readout')).toHaveTextContent('м12 · 13 ₽');
});

test('kpi delta colour is inverted when higher is not better', () => {
  const kpi: StatsKpi = { key: 'c', label: 'Отменено', value: 3, unit: 'count', delta_pct: 50, compare: true, higher_is_better: false };
  const { rerender } = render(<KpiTile kpi={kpi} />);
  expect(screen.getByText('▲ 50% к прошлому периоду')).toHaveClass('down');
  rerender(<KpiTile kpi={{ ...kpi, delta_pct: -50 }} />);
  expect(screen.getByText('▼ 50% к прошлому периоду')).toHaveClass('up');
  rerender(<KpiTile kpi={{ ...kpi, delta_pct: -50, higher_is_better: true }} />);
  expect(screen.getByText('▼ 50% к прошлому периоду')).toHaveClass('down');
});

test('ranked rows with equal labels render without duplicate key warnings', () => {
  const err = vi.spyOn(console, 'error').mockImplementation(() => {});
  render(<StatsChart chart={chart({ kind: 'hbars', unit: 'hours', labels: ['Иванов', 'Иванов'], series: [{ name: 'x', values: [6, 3] }] })} />);
  expect(err).not.toHaveBeenCalled();
  err.mockRestore();
});
