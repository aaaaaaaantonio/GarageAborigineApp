import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { ROLE_LABELS } from '../lib/labels';
import { Button } from '../ui/Button';
import { ScreenHeader } from '../ui/ScreenHeader';

export function MoreScreen() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  return (
    <>
      <ScreenHeader title="Ещё" />
      <div className="stack">
        <div className="card">
          <b>{user!.full_name}</b>
          <span className="hint">{ROLE_LABELS[user!.role]}</span>
        </div>
        <Link className="btn btn-block" to="/clients/new">Новый клиент</Link>
        <Link className="btn btn-block" to="/consent/paper">Бумажное согласие</Link>
        {user!.role === 'admin' && <Link className="btn btn-block" to="/staff/new">Добавить сотрудника</Link>}
        <Button
          variant="ghost"
          block
          onClick={() => {
            signOut();
            navigate('/login', { replace: true });
          }}
        >
          Выйти
        </Button>
      </div>
    </>
  );
}
