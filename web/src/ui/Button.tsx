import type { ButtonHTMLAttributes } from 'react';

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  busy?: boolean;
  block?: boolean;
}

export function Button({ variant = 'secondary', busy = false, block = false, disabled, className = '', type = 'button', ...rest }: Props) {
  const classes = ['btn', `btn-${variant}`, block ? 'btn-block' : '', className].filter(Boolean).join(' ');
  return <button type={type} className={classes} disabled={disabled || busy} aria-busy={busy || undefined} {...rest} />;
}
