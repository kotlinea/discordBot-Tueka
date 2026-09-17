import type { InputHTMLAttributes } from 'react'

export type FieldConstraints = { minLength?: number; maxLength?: number; minimum?: number; maximum?: number; pattern?: string }

export function inputAttributes(value: FieldConstraints): Pick<InputHTMLAttributes<HTMLInputElement>, 'minLength' | 'maxLength' | 'min' | 'max' | 'pattern'> {
  return { minLength: value.minLength, maxLength: value.maxLength, min: value.minimum, max: value.maximum, pattern: value.pattern }
}
