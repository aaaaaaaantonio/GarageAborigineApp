import { useState } from 'react';
import { visitsApi } from '../api/endpoints';
import { useAction } from '../lib/useAction';
import { Button } from '../ui/Button';
import { Field } from '../ui/Field';
import { Sheet } from '../ui/Sheet';

export function CancelVisitSheet({ visitId, open, onClose }: { visitId: string; open: boolean; onClose: () => void }) {
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const cancel = useAction(() => visitsApi.changeStatus(visitId, 'cancelled', reason.trim()), {
    invalidate: [['visit', visitId], ['visits']],
    onSuccess: onClose,
  });
  return (
    <Sheet open={open} title="Отменить заезд" onClose={onClose}>
      <form
        className="form"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          if (!reason.trim()) {
            setError('Укажите причину');
            return;
          }
          setError('');
          cancel.mutate();
        }}
      >
        <Field label="Причина отмены" value={reason} onChange={(e) => setReason(e.target.value)} error={error} autoFocus />
        <Button type="submit" variant="danger" block busy={cancel.isPending}>Отменить заезд</Button>
      </form>
    </Sheet>
  );
}
