import { useEffect, useState, useCallback } from 'react'
import { getPendingItems, type OutboxItem } from './outbox'

// Polling, not an event bus -- matches this app's existing pattern
// (AssistantHomePage already polls its own list every 6s) rather than
// introducing a new pub-sub layer just for this. IndexedDB reads are cheap
// and this only needs to be "reasonably fresh," not real-time.
export function useOutboxSummary(intervalMs = 3000) {
  const [items, setItems] = useState<OutboxItem[]>([])

  const refresh = useCallback(async () => {
    setItems(await getPendingItems())
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, intervalMs)
    return () => clearInterval(id)
  }, [refresh, intervalMs])

  return { items, refresh }
}
