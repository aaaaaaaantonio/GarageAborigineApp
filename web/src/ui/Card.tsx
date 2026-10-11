import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

export function Card({ to, children, className = '' }: { to?: string; children: ReactNode; className?: string }) {
  if (to) {
    return <Link to={to} className={`card card-link ${className}`.trim()}>{children}</Link>;
  }
  return <div className={`card ${className}`.trim()}>{children}</div>;
}
