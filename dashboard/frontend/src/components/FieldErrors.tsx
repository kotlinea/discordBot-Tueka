import { ApiError } from '../api'

export function FieldErrors({ error }: { error: unknown }) {
  if (!(error instanceof ApiError) || !error.fields.length) return null
  return <ul>{error.fields.map((field, index) => <li key={`${field.path}-${index}`}>
    {field.path && <strong>{field.path}: </strong>}{field.message}
  </li>)}</ul>
}
