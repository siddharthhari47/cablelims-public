import { Alert } from '@mantine/core'
import { IconWifiOff } from '@tabler/icons-react'

function relativeTime(fromMs: number): string {
  const seconds = Math.max(0, Math.round((Date.now() - fromMs) / 1000))
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? '' : 's'} ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`
  const days = Math.round(hours / 24)
  return `${days} day${days === 1 ? '' : 's'} ago`
}

// Shown inline by a page when IT is currently serving IndexedDB-cached data
// instead of a live server response (a fetch failed at the network level --
// see AssistantHomePage/AssistantSamplePage's load()). Deliberately per-page
// rather than a single persistent shell-level banner: only the page itself
// knows whether what it's showing right now is live or cached, and a sample
// detail page can be stale while the list just loaded fine a moment earlier
// (or vice versa) -- a global banner can't express that distinction.
export function OfflineBanner({ cachedAt }: { cachedAt: number }) {
  return (
    <Alert color="orange" icon={<IconWifiOff size={16} />} variant="light">
      Offline — showing cached data from {relativeTime(cachedAt)}
    </Alert>
  )
}
