import type { ReactNode } from 'react';
import { useGoBack } from '../lib/useGoBack';
import { telegram } from '../telegram/webapp';

export function ScreenHeader({ title, back = false, onBack, right }: { title: string; back?: boolean; onBack?: () => void; right?: ReactNode }) {
  const goBack = useGoBack();
  return (
    <header className="screen-header">
      {back && !telegram.isMiniApp() && (
        <button type="button" className="back" aria-label="Назад" onClick={onBack ?? goBack}>‹</button>
      )}
      <h1>{title}</h1>
      {right}
    </header>
  );
}
