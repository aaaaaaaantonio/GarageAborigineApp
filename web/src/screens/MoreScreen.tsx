import { Link } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { ROLE_LABELS } from '../lib/labels';
import { ScreenHeader } from '../ui/ScreenHeader';

export function MoreScreen() {
  const { user } = useAuth();
  return (
    <>
      <ScreenHeader title="Ещё" />
      <div className="stack">
        <div className="card">
          <b>{user!.full_name}</b>
          <span className="hint">{ROLE_LABELS[user!.role]}</span>
        </div>
        <Link className="btn btn-block" to="/works">Доска работ</Link>
        <Link className="btn btn-block" to="/visits/archive">Архив заездов</Link>
        <Link className="btn btn-block" to="/clients/new">Новый клиент</Link>
        <Link className="btn btn-block" to="/consent/paper">Бумажное согласие</Link>
        {user!.role === 'admin' && (
          <>
            <Link className="btn btn-block" to="/my">Мои работы</Link>
            <Link className="btn btn-block" to="/my/done">Мои выполненные</Link>
            <Link className="btn btn-block" to="/staff/new">Добавить сотрудника</Link>
          </>
        )}
      </div>
    </>
  );
}
