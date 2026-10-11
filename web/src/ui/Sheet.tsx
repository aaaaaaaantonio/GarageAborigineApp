import type { ReactNode } from 'react';
import { Button } from './Button';

export function Sheet({ open, title, onClose, children }: { open: boolean; title: string; onClose: () => void; children: ReactNode }) {
  if (!open) return null;
  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <div className="sheet-title">{title}</div>
        {children}
        <Button variant="ghost" block onClick={onClose}>Закрыть</Button>
      </div>
    </div>
  );
}
