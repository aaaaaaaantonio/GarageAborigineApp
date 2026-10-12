import { useMutation } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { consentApi } from '../api/endpoints';
import { PHONE_FORMAT_ERROR, isValidPhone } from '../lib/validators';
import { telegram } from '../telegram/webapp';
import { Button } from '../ui/Button';
import { Field } from '../ui/Field';
import { ScreenHeader } from '../ui/ScreenHeader';
import { NO_ERRORS, toFormErrors, type FormErrors } from './formErrors';

export function PaperConsentForm() {
  const navigate = useNavigate();
  const [phone, setPhone] = useState('');
  const [fullName, setFullName] = useState('');
  const [errors, setErrors] = useState<FormErrors>(NO_ERRORS);
  const save = useMutation({
    mutationFn: () => consentApi.paper(fullName.trim(), phone.trim()),
    onSuccess: (r) => {
      telegram.haptic('success');
      navigate(`/clients/${r.client_id}`, { replace: true });
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
    <>
      <ScreenHeader title="Бумажное согласие" back />
      <p className="hint">Клиент подписал согласие на бумаге — зарегистрируйте его.</p>
      <form className="form" noValidate onSubmit={submit}>
        <Field label="Телефон" type="tel" inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} error={errors.fields.phone} />
        <Field label="ФИО" value={fullName} onChange={(e) => setFullName(e.target.value)} error={errors.fields.full_name} />
        {errors.general && <p className="form-error" role="alert">{errors.general}</p>}
        <Button type="submit" variant="primary" block busy={save.isPending}>Зарегистрировать</Button>
      </form>
    </>
  );
}
