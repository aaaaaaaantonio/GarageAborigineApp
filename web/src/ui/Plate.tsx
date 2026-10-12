import { looksLikePlate, normalizePlate } from '../lib/validators';

export function Plate({ value }: { value: string }) {
  const plate = normalizePlate(value);
  if (!looksLikePlate(plate)) return <span className="plate plate-raw">{value}</span>;
  return (
    <span className="plate" aria-label={`Госномер ${plate}`}>
      {plate.slice(0, 6)}
      <small>{plate.slice(6)}</small>
    </span>
  );
}
