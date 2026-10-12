import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { workItemsApi } from '../api/endpoints';
import type { PartItemCreate } from '../api/types';
import { parseNumber } from '../lib/format';
import { telegram } from '../telegram/webapp';
import { Button } from '../ui/Button';
import { Field } from '../ui/Field';
import { ScreenHeader } from '../ui/ScreenHeader';
import { NO_ERRORS, toFormErrors, type FormErrors } from './formErrors';

export function AddPartForm() {
  const { visitId = '', itemId = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [quantity, setQuantity] = useState('1');
  const [price, setPrice] = useState('');
  const [errors, setErrors] = useState<FormErrors>(NO_ERRORS);
  const save = useMutation({
    mutationFn: (body: PartItemCreate) => workItemsApi.addPart(visitId, body),
    onSuccess: async () => {
      telegram.haptic('success');
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['visit', visitId] }),
        queryClient.invalidateQueries({ queryKey: ['visitLines', visitId] }),
      ]);
      navigate(`/visits/${visitId}/works/${itemId}`, { replace: true });
    },
    onError: (e) => {
      telegram.haptic('error');
      setErrors(toFormErrors(e, ['name', 'quantity', 'unit_price']));
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    const q = parseNumber(quantity);
    const p = parseNumber(price);
    const fields: Record<string, string> = {};
    if (!name.trim()) fields.name = 'Введите название запчасти';
    if (q === null || q < 1 || !Number.isInteger(q)) fields.quantity = 'Количество — целое число от 1';
    if (p === null || p < 0) fields.unit_price = 'Цена — число';
    if (Object.keys(fields).length) {
      setErrors({ fields, general: '' });
      return;
    }
    setErrors(NO_ERRORS);
    save.mutate({ work_item_id: itemId, name: name.trim(), quantity: q!, unit_price: p! });
  }

  return (
    <>
      <ScreenHeader title="Новая запчасть" back />
      <form className="form" noValidate onSubmit={submit}>
        <Field label="Название" value={name} onChange={(e) => setName(e.target.value)} error={errors.fields.name} />
        <Field label="Количество" inputMode="numeric" value={quantity} onChange={(e) => setQuantity(e.target.value)} error={errors.fields.quantity} />
        <Field label="Цена за штуку, ₽" inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} error={errors.fields.unit_price} />
        {errors.general && <p className="form-error" role="alert">{errors.general}</p>}
        <Button type="submit" variant="primary" block busy={save.isPending}>Добавить запчасть</Button>
      </form>
    </>
  );
}
