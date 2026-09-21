import type { ComponentProps } from 'react'
import s from '../../styles/App.module.css'

type Props = ComponentProps<'button'> & { variant?: 'primary' | 'secondary' | 'danger' | 'icon'; loading?: boolean }
const variants = { primary: s.primaryButton, secondary: s.secondaryButton, danger: s.dangerButton, icon: s.iconButton }

export function Button({ variant = 'secondary', loading = false, disabled, type = 'button', className = '', children, ...props }: Props) {
  return <button {...props} type={type} disabled={disabled || loading} aria-busy={loading || undefined} className={`${variants[variant]} ${className}`}>
    {loading && <span className={s.spinner} aria-hidden="true"/>}{children}
  </button>
}
