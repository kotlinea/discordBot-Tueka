/** Wait for a lazy screen's heading after closing an overlay navigation. */
export function focusPageHeading(previous?: Element | null) {
  const observer = new MutationObserver(focus)
  function focus() {
    const heading = document.querySelector<HTMLElement>('[data-workspace] main h1')
    if (!heading?.getClientRects().length || heading === previous) return
    heading.tabIndex = -1
    heading.focus()
    observer.disconnect()
  }
  observer.observe(document.body, { childList: true, subtree: true, attributes: true })
  focus()
  return () => observer.disconnect()
}
