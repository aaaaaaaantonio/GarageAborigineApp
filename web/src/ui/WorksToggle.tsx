import { NavLink } from 'react-router-dom';

/** «Мои работы» is one section: current work and finished work are two views of it. */
export function WorksToggle() {
  return (
    <nav className="seg" aria-label="Вид">
      <NavLink to="/my" end>Текущие</NavLink>
      <NavLink to="/my/done">Выполненные</NavLink>
    </nav>
  );
}
