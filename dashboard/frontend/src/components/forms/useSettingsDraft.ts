import { useEffect, useRef, useState } from 'react'

const equal = (left: unknown, right: unknown) => JSON.stringify(left) === JSON.stringify(right)

/** A server refresh updates a clean draft; only an explicit discard replaces local edits. */
export function useSettingsDraft<T>(source: T | undefined, initial: T, identity: string, externalDirty = false) {
  const [baseline, setBaseline] = useState(source ?? initial)
  const [draft, setDraft] = useState(source ?? initial)
  const previous = useRef({ identity, source })
  const dirty = externalDirty || !equal(draft, baseline)
  useEffect(() => {
    const old = previous.current
    previous.current = { identity, source }
    if (old.identity !== identity) {
      setBaseline(source ?? initial)
      setDraft(source ?? initial)
    } else if (source !== undefined && old.source !== source && !dirty && !equal(source, baseline)) {
      setBaseline(source)
      setDraft(source)
    }
  }, [source, initial, identity, dirty, baseline])
  const accept = (value: T) => { setBaseline(value); setDraft(value) }
  return { draft, setDraft, baseline, dirty, accept,
    discard: () => accept(source ?? baseline),
    changedRemotely: dirty && source !== undefined && !equal(source, baseline) }
}
