import { useMutation } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { clientsApi } from '../api/endpoints';
import type { Client } from '../api/types';
import { PHONE_FORMAT_ERROR, isValidPhone } from '../lib/validators';
import { telegram } from '../telegram/webapp';
import { Button } from '../ui/Button';
import { Field } from '../ui/Field';
import { NO_ERRORS, toFormErrors, type FormErrors } from './formErrors';

interface Props {
  initialQuery?: string;
  submitLabel?: string;
  onCreated: (client: Client) => void;
}

export function ClientForm({ initialQuery = '', submitLabel = 'Создать клиента', onCreated }: Props) {
  const queryIsPhone = isValidPhone(initialQuery);
  const [phone, setPhone] = useState(queryIsPhone ? initialQuery : '');
  const [fullName, setFullName] = useState(queryIsPhone ? '' : initialQuery);
  const [errors, setErrors] = useState<FormErrors>(NO_ERRORS);
  const save = useMutation({
    mutationFn: () => clientsApi.create(fullName.trim(), phone.trim()),
    onSuccess: (client) => {
      telegram.haptic('success');
      onCreated(client);
    },
    onError: (e) => {
      telegram.haptic('error');
      setErrors(toFormErrors(e, ['phone', 'full_name'], 'phone'));
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    const fields: Record<string, string> = {};
    if (!isValidPhone(phone)) fields.phone = PHONE_FORMAT_ERROR;
    if (!fullName.trim()) fields.full_name = 'Введите ФИО';
    if (Object.keys(fields).length) {
      setErrors({ fields, general: '' });
      return;
    }
    setErrors(NO_ERRORS);
    save.mutate();
  }

  return (
    <form className="form" noValidate onSubmit={submit}>
      <Field label="Телефон" type="tel" inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} error={errors.fields.phone} />
      <Field label="ФИО" value={fullName} onChange={(e) => setFullName(e.target.value)} error={errors.fields.full_name} />
      {errors.general && <p className="form-error" role="alert">{errors.general}</p>}
      <Button type="submit" variant="primary" block busy={save.isPending}>{submitLabel}</Button>
    </form>
  );
}
