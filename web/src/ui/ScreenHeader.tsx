import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { useGoBack } from '../lib/useGoBack';
import { telegram } from '../telegram/webapp';

/** Who is signed in, and the way out; shown on tab roots for every role. */
function Account() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;
  return (
    <span className="account">
      <span className="account-name" title={user.full_name}>{user.full_name}</span>
      <button
        type="button"
        className="account-exit"
        onClick={() => {
          signOut();
          navigate('/login', { replace: true });
        }}
      >
        Выйти
      </button>
    </span>
  );
}

/** Title centred; left: back (inner screens), right: `right` or, on tab roots, the account. */
export function ScreenHeader({ title, back = false, onBack, right }: { title: string; back?: boolean; onBack?: () => void; right?: ReactNode }) {
  const goBack = useGoBack();
  return (
    <header className="screen-header">
      <div className="screen-header-side">
        {back && !telegram.isMiniApp() && (
          <button type="button" className="back" aria-label="Назад" onClick={onBack ?? goBack}>‹</button>
        )}
      </div>
      <h1>{title}</h1>
      <div className="screen-header-side screen-header-right">{right ?? (back ? null : <Account />)}</div>
    </header>
  );
}
