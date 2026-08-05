import { api, extractErrorMessage } from '../api/client'
import { isNetworkError } from './isNetworkError'
import { getPendingItems, markSyncing, markSynced, markFailed, type OutboxItem } from './outbox'
import { sendProfile, sendMarkingImage, sendDiagramImage, sendTestSubmit } from './sends'
import { putCachedSampleDetail } from './db'
import type { SampleDetail } from '../types'

const BASE_BACKOFF_MS = 2000
const MAX_BACKOFF_MS = 120_000

// A 'failed'+'transient' item (network-level failure) is retried with
// exponential backoff, capped -- the network WILL eventually come back, so
// there's no attempt limit, just a growing delay between tries so a
// still-offline device doesn't hammer itself. A 'failed'+'rejected' item
// (a real HTTP error -- most importantly a now-locked sample, see
// outbox.ts's coalescing comment) is NEVER auto-retried here; see
// phase 4's sync status UI for the explicit "Retry now" / "Discard" actions.
function isReadyForRetry(item: OutboxItem): boolean {
  if (item.status === 'pending') return true
  if (item.status === 'failed' && item.errorKind === 'transient') {
    const delay = Math.min(BASE_BACKOFF_MS * 2 ** item.attempts, MAX_BACKOFF_MS)
    return Date.now() - item.updatedAt >= delay
  }
  return false
}

// Profile before images before test-submits (submit_reading requires the
// profile to already exist server-side -- see sample_service.py), ties
// broken by creation order. Images have no ordering dependency on anything
// else, so they share a tier between profile and test-submits.
const KIND_TIER: Record<OutboxItem['kind'], number> = {
  PROFILE: 0, MARKING_IMAGE: 1, DIAGRAM_IMAGE: 1, TEST_SUBMIT: 2,
}

function sortForSync(items: OutboxItem[]): OutboxItem[] {
  return [...items].sort((a, b) => (KIND_TIER[a.kind] - KIND_TIER[b.kind]) || (a.createdAt - b.createdAt))
}

async function sendItem(item: OutboxItem) {
  switch (item.kind) {
    case 'PROFILE':
      return sendProfile(item.sampleId, item.payload)
    case 'MARKING_IMAGE': {
      const p = item.payload as { blob: Blob; filename: string }
      return sendMarkingImage(item.sampleId, p.blob, p.filename)
    }
    case 'DIAGRAM_IMAGE': {
      const p = item.payload as { blob: Blob; filename: string }
      return sendDiagramImage(item.sampleId, p.blob, p.filename)
    }
    case 'TEST_SUBMIT': {
      const p = item.payload as { raw_values: Record<string, unknown> }
      if (!item.assignedTestId) throw new Error('TEST_SUBMIT outbox item is missing assignedTestId')
      return sendTestSubmit(item.sampleId, item.assignedTestId, p.raw_values, item.id)
    }
  }
}

// Best-effort: pulls the just-synced sample's real, server-computed state
// (assigned tests, calculated results, possibly a flipped status) into the
// read cache, rather than hand-patching the complex derived state
// client-side -- the server is the only thing that actually knows it
// (the rule engine, calculation engine, etc. all run server-side).
async function refreshSampleCache(sampleId: string): Promise<void> {
  try {
    const res = await api.get(`/samples/${sampleId}`)
    await putCachedSampleDetail(res.data as SampleDetail)
  } catch {
    // Fine -- the next normal page load refetches anyway.
  }
}

let syncInProgress = false

export async function runSyncPass(): Promise<void> {
  if (syncInProgress) return
  syncInProgress = true
  try {
    const pending = (await getPendingItems()).filter(isReadyForRetry)
    const bySample = new Map<string, OutboxItem[]>()
    for (const item of pending) {
      const list = bySample.get(item.sampleId) ?? []
      list.push(item)
      bySample.set(item.sampleId, list)
    }

    await Promise.all(
      Array.from(bySample.entries()).map(async ([sampleId, items]) => {
        let anySynced = false
        for (const item of sortForSync(items)) {
          await markSyncing(item)
          try {
            await sendItem(item)
            await markSynced(item)
            anySynced = true
          } catch (err) {
            if (isNetworkError(err)) {
              await markFailed(item, 'transient', 'No connection to the server yet -- will retry automatically.')
            } else {
              await markFailed(item, 'rejected', extractErrorMessage(err))
            }
            // Stop-on-first-failure for this sample, this pass: a failed
            // PROFILE/image blocks anything ordered after it, and a
            // transient network failure means everything else queued for
            // this sample would fail identically right now anyway. Left
            // 'pending'/'failed' items are picked up again on the next pass.
            break
          }
        }
        if (anySynced) await refreshSampleCache(sampleId)
      }),
    )
  } finally {
    syncInProgress = false
  }
}

// Reconnection is the primary trigger for a sync pass beyond the explicit
// calls after a successful page load/poll (AssistantHomePage,
// AssistantSamplePage) and right after queueOrSend.ts enqueues something.
if (typeof window !== 'undefined') {
  window.addEventListener('online', () => {
    runSyncPass().catch(() => { /* best-effort; failures just leave items queued for the next trigger */ })
  })
}
