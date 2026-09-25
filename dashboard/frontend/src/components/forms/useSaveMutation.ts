import { useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import type { UseMutationOptions } from '@tanstack/react-query'

/** Prevent a second submission before React has painted the pending state. */
export function useSaveMutation<T, V = void>(options: UseMutationOptions<T, Error, V>) {
  const busy = useRef(false)
  const mutation = useMutation(options)
  return { ...mutation, mutate: (value: V) => {
    if (busy.current) return
    busy.current = true
    mutation.mutate(value, { onSettled: () => { busy.current = false } })
  } }
}
