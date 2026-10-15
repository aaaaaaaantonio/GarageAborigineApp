import { NavLink } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';

const STAFF_TABS = [
  { to: '/visits', icon: '🔧', label: 'Заезды', end: true },
  { to: '/search', icon: '🔍', label: 'Поиск', end: false },
  { to: '/visits/new', icon: '＋', label: 'Заезд', end: false },
  { to: '/more', icon: '☰', label: 'Ещё', end: false },
];
const MECHANIC_TABS = [
  { to: '/my', icon: '🧰', label: 'Мои работы', end: true },
  { to: '/my/done', icon: '✅', label: 'Выполненные', end: false },
  { to: '/stats', icon: '📊', label: 'Статистика', end: false },
  { to: '/search', icon: '🔍', label: 'Поиск', end: false },
];

export function TabBar() {
  const { user } = useAuth();
  const tabs = user?.role === 'mechanic' ? MECHANIC_TABS : STAFF_TABS;
  return (
    <nav className="tabbar" aria-label="Разделы">
      {tabs.map((t) => (
        <NavLink key={t.to} to={t.to} end={t.end}>
          <span className="tab-icon" aria-hidden="true">{t.icon}</span>
          <span>{t.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
