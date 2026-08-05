import { isNetworkError } from './isNetworkError'
import { enqueue, type EnqueueInput } from './outbox'
import { runSyncPass } from './syncEngine'

export type QueueOrSendResult<T> =
  | { status: 'sent'; data: T }
  | { status: 'queued' }

// Tries the real API call first. Only on a genuine network-level failure
// (see isNetworkError.ts) does it fall back to enqueueing -- any real HTTP
// error (422 validation, 400 locked-sample, etc.) is re-thrown unchanged so
// existing error handling at the call site keeps working exactly as before
// offline support existed.
export async function queueOrSend<T>(
  send: () => Promise<T>,
  buildOutboxItem: () => EnqueueInput,
): Promise<QueueOrSendResult<T>> {
  try {
    const data = await send()
    return { status: 'sent', data }
  } catch (err) {
    if (!isNetworkError(err)) throw err
    await enqueue(buildOutboxItem())
    // Fire-and-forget: this item is almost certainly still unreachable
    // (we just failed to reach the server 5ms ago), so this is not expected
    // to succeed -- it's here for the rare case a flaky connection recovers
    // between the failed live call and now, so the item doesn't sit idle
    // until the next natural sync trigger.
    runSyncPass().catch(() => { /* best-effort; a real failure here just leaves the item queued for the next trigger */ })
    return { status: 'queued' }
  }
}
