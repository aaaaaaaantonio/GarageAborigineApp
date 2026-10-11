import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { catalogApi, usersApi, workItemsApi } from '../api/endpoints';
import type { CatalogItem, WorkCategory, WorkItemCreate } from '../api/types';
import { parseNumber } from '../lib/format';
import { WORK_CATEGORY_LABELS } from '../lib/labels';
import { useDebounced } from '../lib/useDebounced';
import { telegram } from '../telegram/webapp';
import { Button } from '../ui/Button';
import { Field } from '../ui/Field';
import { ScreenHeader } from '../ui/ScreenHeader';
import { SelectField } from '../ui/SelectField';
import { NO_ERRORS, toFormErrors, type FormErrors } from './formErrors';

const KNOWN = ['free_text_name', 'category', 'norm_hours', 'hourly_rate', 'assigned_mechanic_id'];
const CATEGORY_OPTIONS = [
  { value: '', label: 'Выберите…' },
  ...Object.entries(WORK_CATEGORY_LABELS).map(([value, label]) => ({ value, label })),
];

export function AddWorkForm() {
  const { visitId = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [picked, setPicked] = useState<CatalogItem | null>(null);
  const [category, setCategory] = useState<WorkCategory | ''>('');
  const [hours, setHours] = useState('');
  const [rate, setRate] = useState('');
  const [mechanicId, setMechanicId] = useState('');
  const [errors, setErrors] = useState<FormErrors>(NO_ERRORS);
  const debouncedName = useDebounced(name.trim(), 300);
  const suggestions = useQuery({
    queryKey: ['catalog', debouncedName],
    queryFn: () => catalogApi.suggest(debouncedName),
    enabled: !picked && debouncedName.length >= 2,
  });
  const mechanics = useQuery({ queryKey: ['mechanics'], queryFn: usersApi.mechanics });
  const save = useMutation({
    mutationFn: (body: WorkItemCreate) => workItemsApi.add(visitId, body),
    onSuccess: async () => {
      telegram.haptic('success');
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['workItems', visitId] }),
        queryClient.invalidateQueries({ queryKey: ['visit', visitId] }),
        queryClient.invalidateQueries({ queryKey: ['visitLines', visitId] }),
      ]);
      navigate(`/visits/${visitId}`, { replace: true });
    },
    onError: (e) => {
      telegram.haptic('error');
      setErrors(toFormErrors(e, KNOWN));
    },
  });

  function pick(item: CatalogItem) {
    setPicked(item);
    setName(item.name);
    setCategory(item.category);
    setHours(String(item.default_norm_hours));
  }

  function changeName(value: string) {
    setName(value);
    if (picked && value !== picked.name) setPicked(null);
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    const h = parseNumber(hours);
    const r = parseNumber(rate);
    const fields: Record<string, string> = {};
    if (!name.trim()) fields.free_text_name = 'Введите название работы';
    if (!picked && !category) fields.category = 'Выберите категорию';
    if (h === null || h <= 0) fields.norm_hours = 'Нормо-часы — число больше 0';
    if (r === null || r < 0) fields.hourly_rate = 'Ставка — число';
    if (Object.keys(fields).length) {
      setErrors({ fields, general: '' });
      return;
    }
    setErrors(NO_ERRORS);
    save.mutate({
      catalog_item_id: picked?.id ?? null,
      free_text_name: picked ? null : name.trim(),
      category: (picked?.category ?? category) as WorkCategory,
      norm_hours: h!,
      hourly_rate: r!,
      assigned_mechanic_id: mechanicId || null,
    });
  }

  return (
    <>
      <ScreenHeader title="Новая работа" back />
      <form className="form" noValidate onSubmit={submit}>
        <Field label="Название" value={name} autoComplete="off" onChange={(e) => changeName(e.target.value)}
          error={errors.fields.free_text_name} hint={picked ? 'Из справочника' : undefined} />
        {!picked && suggestions.data && suggestions.data.length > 0 && (
          <div className="suggest" role="listbox" aria-label="Справочник работ">
            {suggestions.data.map((s) => (
              <button key={s.id} type="button" role="option" aria-selected={false} onClick={() => pick(s)}>
                {s.name} <span className="hint">· {s.default_norm_hours} н/ч</span>
              </button>
            ))}
          </div>
        )}
        {!picked && (
          <SelectField label="Категория" value={category} options={CATEGORY_OPTIONS}
            onChange={(e) => setCategory(e.target.value as WorkCategory | '')} error={errors.fields.category} />
        )}
        <Field label="Нормо-часы" inputMode="decimal" value={hours} onChange={(e) => setHours(e.target.value)} error={errors.fields.norm_hours} />
        <Field label="Ставка, ₽/ч" inputMode="decimal" value={rate} onChange={(e) => setRate(e.target.value)} error={errors.fields.hourly_rate} />
        <SelectField label="Исполнитель" value={mechanicId} onChange={(e) => setMechanicId(e.target.value)}
          error={errors.fields.assigned_mechanic_id}
          options={[{ value: '', label: 'Без исполнителя' }, ...(mechanics.data ?? []).map((m) => ({ value: m.id, label: m.full_name }))]} />
        {errors.general && <p className="form-error" role="alert">{errors.general}</p>}
        <Button type="submit" variant="primary" block busy={save.isPending}>Добавить работу</Button>
      </form>
    </>
  );
}
