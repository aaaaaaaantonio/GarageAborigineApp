import { useMutation } from '@tanstack/react-query';
import { useRef, useState, type FormEvent } from 'react';
import { vehiclesApi } from '../api/endpoints';
import type { Vehicle } from '../api/types';
import {
  PLATE_FORMAT_ERROR, VIN_FORMAT_ERROR, isValidVin, looksLikePlate, normalizePlate, normalizeVin,
} from '../lib/validators';
import { telegram } from '../telegram/webapp';
import { Button } from '../ui/Button';
import { Field } from '../ui/Field';
import { NO_ERRORS, toFormErrors, type FormErrors } from './formErrors';

interface Props {
  clientId?: string;
  initialQuery?: string;
  submitLabel?: string;
  onCreated: (vehicle: Vehicle) => void;
}

export function VehicleForm({ clientId, initialQuery = '', submitLabel = 'Добавить автомобиль', onCreated }: Props) {
  const [vin, setVin] = useState(!looksLikePlate(initialQuery) && isValidVin(initialQuery) ? initialQuery : '');
  const [plate, setPlate] = useState(looksLikePlate(initialQuery) ? initialQuery : '');
  const [make, setMake] = useState('');
  const [model, setModel] = useState('');
  const [errors, setErrors] = useState<FormErrors>(NO_ERRORS);
  const createdRef = useRef<Vehicle | null>(null);
  const save = useMutation({
    mutationFn: async () => {
      if (!createdRef.current) {
        createdRef.current = await vehiclesApi.create({
          vin: normalizeVin(vin), plate_number: normalizePlate(plate), make: make.trim(), model: model.trim(),
        });
      }
      const vehicle = createdRef.current;
      if (clientId) await vehiclesApi.attachOwner(vehicle.id, clientId);
      return vehicle;
    },
    onSuccess: (vehicle) => {
      telegram.haptic('success');
      onCreated(vehicle);
    },
    onError: (e) => {
      telegram.haptic('error');
      setErrors(toFormErrors(e, ['vin', 'plate_number', 'make', 'model'], 'vin'));
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    const fields: Record<string, string> = {};
    if (!isValidVin(vin)) fields.vin = VIN_FORMAT_ERROR;
    if (!looksLikePlate(plate)) fields.plate_number = PLATE_FORMAT_ERROR;
    if (!make.trim()) fields.make = 'Введите марку';
    if (!model.trim()) fields.model = 'Введите модель';
    if (Object.keys(fields).length) {
      setErrors({ fields, general: '' });
      return;
    }
    setErrors(NO_ERRORS);
    save.mutate();
  }

  return (
    <form className="form" noValidate onSubmit={submit}>
      <Field label="VIN или номер кузова" className="mono" autoCapitalize="characters" value={vin} onChange={(e) => setVin(e.target.value)} error={errors.fields.vin} />
      <Field label="Госномер" autoCapitalize="characters" value={plate} onChange={(e) => setPlate(e.target.value)} error={errors.fields.plate_number} />
      <Field label="Марка" value={make} onChange={(e) => setMake(e.target.value)} error={errors.fields.make} />
      <Field label="Модель" value={model} onChange={(e) => setModel(e.target.value)} error={errors.fields.model} />
      {errors.general && <p className="form-error" role="alert">{errors.general}</p>}
      <Button type="submit" variant="primary" block busy={save.isPending}>{submitLabel}</Button>
    </form>
  );
}
