import {
  getAllOutboxItems, getOutboxItemsBySample, putOutboxItem, deleteOutboxItem,
  type OutboxItem, type OutboxKind, type OutboxErrorKind,
} from './db'

export type { OutboxItem, OutboxKind, OutboxStatus, OutboxErrorKind } from './db'

// Kinds where only the LATEST queued item per sample matters -- re-submitting
// the same profile is a verified no-op server-side (sample_service.py's
// submit_profile diffs against unchanged state), and a duplicate image
// upload just orphans a file rather than corrupting logical state, so
// there's nothing gained by keeping an earlier queued edit around once a
// newer one for the same sample has been made. TEST_SUBMIT is deliberately
// NOT in this set -- each one is a distinct, real attempt (see
// sample_service.py's submit_reading docstring on why attempts accumulate
// rather than replace), and the backend's own client_request_id dedupe
// (phase 3a) is what makes a genuine duplicate-enqueue of the SAME attempt
// safe, not coalescing.
const COALESCED_KINDS: ReadonlySet<OutboxKind> = new Set(['PROFILE', 'MARKING_IMAGE', 'DIAGRAM_IMAGE'])

export interface EnqueueInput {
  id: string
  sampleId: string
  kind: OutboxKind
  assignedTestId?: string
  payload: unknown
}

// Enqueues a mutation that failed to send live due to a network-level
// failure. For PROFILE/MARKING_IMAGE/DIAGRAM_IMAGE, replaces any existing
// pending/failed item for the same sample+kind (last-write-wins) rather than
// accumulating stale duplicates.
export async function enqueue(input: EnqueueInput): Promise<OutboxItem> {
  if (COALESCED_KINDS.has(input.kind)) {
    const existing = await getOutboxItemsBySample(input.sampleId)
    const stale = existing.filter((it) => it.kind === input.kind && it.status !== 'synced')
    await Promise.all(stale.map((it) => deleteOutboxItem(it.id)))
  }
  const now = Date.now()
  const item: OutboxItem = {
    id: input.id,
    sampleId: input.sampleId,
    kind: input.kind,
    assignedTestId: input.assignedTestId,
    payload: input.payload,
    status: 'pending',
    createdAt: now,
    updatedAt: now,
    attempts: 0,
  }
  await putOutboxItem(item)
  return item
}

export async function getPendingItems(): Promise<OutboxItem[]> {
  const all = await getAllOutboxItems()
  return all.filter((it) => it.status !== 'synced')
}

export async function markSyncing(item: OutboxItem): Promise<void> {
  await putOutboxItem({ ...item, status: 'syncing', updatedAt: Date.now() })
}

export async function markSynced(item: OutboxItem): Promise<void> {
  await putOutboxItem({ ...item, status: 'synced', updatedAt: Date.now(), lastError: undefined, errorKind: undefined })
}

export async function markFailed(item: OutboxItem, errorKind: OutboxErrorKind, message: string): Promise<void> {
  await putOutboxItem({
    ...item, status: 'failed', updatedAt: Date.now(),
    attempts: item.attempts + 1, errorKind, lastError: message,
  })
}

// Manual re-queue from the phase 4 sync status UI ("Retry now" on a
// transient failure) -- resets to pending so the next sync pass picks it up
// immediately rather than waiting out its backoff window.
export async function markPending(item: OutboxItem): Promise<void> {
  await putOutboxItem({ ...item, status: 'pending', updatedAt: Date.now() })
}

export async function discard(item: OutboxItem): Promise<void> {
  await deleteOutboxItem(item.id)
}
