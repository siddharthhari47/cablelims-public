import { useEffect, useState } from 'react'

// navigator.onLine reflects link-layer connectivity (e.g. Wi-Fi associated),
// not "can actually reach the CableLIMS server" -- it's a coarse signal, not
// a guarantee. It's used here only as a UI hint (the offline banner) and as
// a trigger to retry, never as the sole basis for deciding a request failed
// -- that decision is always made from the actual fetch error (see
// queueOrSend.ts in phase 3), which is the only source of truth.
export function useOnlineStatus(): boolean {
  const [online, setOnline] = useState(navigator.onLine)

  useEffect(() => {
    const goOnline = () => setOnline(true)
    const goOffline = () => setOnline(false)
    window.addEventListener('online', goOnline)
    window.addEventListener('offline', goOffline)
    return () => {
      window.removeEventListener('online', goOnline)
      window.removeEventListener('offline', goOffline)
    }
  }, [])

  return online
}
