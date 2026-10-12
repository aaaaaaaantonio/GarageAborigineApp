import { useMutation } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { usersApi } from '../api/endpoints';
import type { Role } from '../api/types';
import { ROLE_LABELS } from '../lib/labels';
import { telegram } from '../telegram/webapp';
import { Button } from '../ui/Button';
import { Field } from '../ui/Field';
import { ScreenHeader } from '../ui/ScreenHeader';
import { SelectField } from '../ui/SelectField';
import { useToast } from '../ui/Toast';
import { NO_ERRORS, toFormErrors, type FormErrors } from './formErrors';

const ROLE_OPTIONS = (['master', 'mechanic', 'admin'] as Role[]).map((r) => ({ value: r, label: ROLE_LABELS[r] }));

export function StaffForm() {
  const navigate = useNavigate();
  const toast = useToast();
  const [role, setRole] = useState<Role>('master');
  const [fullName, setFullName] = useState('');
  const [telegramId, setTelegramId] = useState('');
  const [errors, setErrors] = useState<FormErrors>(NO_ERRORS);
  const save = useMutation({
    mutationFn: () => usersApi.create({ role, full_name: fullName.trim(), telegram_id: Number(telegramId.trim()) }),
    onSuccess: () => {
      telegram.haptic('success');
      toast.show('Сотрудник добавлен');
      navigate('/more', { replace: true });
    },
    onError: (e) => {
      telegram.haptic('error');
      setErrors(toFormErrors(e, ['role', 'full_name', 'telegram_id'], 'telegram_id'));
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    const fields: Record<string, string> = {};
    if (!fullName.trim()) fields.full_name = 'Введите ФИО';
    if (!/^\d{5,15}$/.test(telegramId.trim())) fields.telegram_id = 'Telegram ID — число (узнать: @userinfobot)';
    if (Object.keys(fields).length) {
      setErrors({ fields, general: '' });
      return;
    }
    setErrors(NO_ERRORS);
    save.mutate();
  }

  return (
    <>
      <ScreenHeader title="Новый сотрудник" back />
      <form className="form" noValidate onSubmit={submit}>
        <SelectField label="Роль" value={role} options={ROLE_OPTIONS} onChange={(e) => setRole(e.target.value as Role)} />
        <Field label="ФИО" value={fullName} onChange={(e) => setFullName(e.target.value)} error={errors.fields.full_name} />
        <Field label="Telegram ID" inputMode="numeric" value={telegramId} onChange={(e) => setTelegramId(e.target.value)} error={errors.fields.telegram_id} />
        {errors.general && <p className="form-error" role="alert">{errors.general}</p>}
        <Button type="submit" variant="primary" block busy={save.isPending}>Добавить сотрудника</Button>
      </form>
    </>
  );
}
