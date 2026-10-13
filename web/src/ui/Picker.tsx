import { SelectField } from './SelectField';

interface Props<T extends string> {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}

/** One-of-many choice as a labelled drop-down (filters, sorting, grouping). */
export function Picker<T extends string>({ label, value, options, onChange }: Props<T>) {
  return <SelectField label={label} value={value} options={options} onChange={(e) => onChange(e.target.value as T)} />;
}
