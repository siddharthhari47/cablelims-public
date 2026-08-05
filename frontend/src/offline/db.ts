import { openDB, type DBSchema, type IDBPDatabase } from 'idb'
import type { SampleListItem, SampleDetail } from '../types'

// Offline support, phase 2: a purpose-built cache for exactly the two GETs
// the Scientific Assistant flow makes (sample list, sample detail) plus the
// one authenticated binary GET (diagram image) -- not a generic URL/response
// cache. This lets the read side reason about "do I have this sample's
// detail," which phase 3's write outbox also needs (to patch in optimistic
// state once a queued mutation is enqueued/synced), rather than opaque
// cached HTTP responses.
//
// Phase 3b adds `outbox`: one row per queued-while-offline mutation
// (profile submit, marking/diagram image upload, test reading submit). See
// offline/outbox.ts for the coalescing/enqueue logic built on top of the
// primitives below, and offline/syncEngine.ts for how items get replayed.
export type OutboxKind = 'PROFILE' | 'MARKING_IMAGE' | 'DIAGRAM_IMAGE' | 'TEST_SUBMIT'
export type OutboxStatus = 'pending' | 'syncing' | 'failed' | 'synced'
export type OutboxErrorKind = 'transient' | 'rejected'

export interface OutboxItem {
  id: string
  sampleId: string
  kind: OutboxKind
  // Only set (and only meaningful) for TEST_SUBMIT -- which assigned test
  // this reading belongs to.
  assignedTestId?: string
  // JSON body for PROFILE/TEST_SUBMIT ({ ... profile fields } / { raw_values
  // }); { blob, filename } for the two image kinds -- idb stores Blobs
  // natively, no base64 encoding needed.
  payload: unknown
  status: OutboxStatus
  createdAt: number
  updatedAt: number
  attempts: number
  lastError?: string
  errorKind?: OutboxErrorKind
}

interface CableLimsOfflineDB extends DBSchema {
  samples: {
    key: string
    value: SampleListItem & { _cachedAt: number }
  }
  sampleDetail: {
    key: string
    value: SampleDetail & { _cachedAt: number }
  }
  images: {
    key: string
    value: { key: string; blob: Blob; contentType: string; _cachedAt: number }
  }
  outbox: {
    key: string
    value: OutboxItem
    indexes: { 'by-sample': string; 'by-status': string }
  }
}

const DB_NAME = 'cablelims-offline'
const DB_VERSION = 2

let dbPromise: Promise<IDBPDatabase<CableLimsOfflineDB>> | null = null

function getDB() {
  if (!dbPromise) {
    dbPromise = openDB<CableLimsOfflineDB>(DB_NAME, DB_VERSION, {
      upgrade(db) {
        if (!db.objectStoreNames.contains('samples')) db.createObjectStore('samples', { keyPath: 'sample_id' })
        if (!db.objectStoreNames.contains('sampleDetail')) db.createObjectStore('sampleDetail', { keyPath: 'sample_id' })
        if (!db.objectStoreNames.contains('images')) db.createObjectStore('images', { keyPath: 'key' })
        if (!db.objectStoreNames.contains('outbox')) {
          const store = db.createObjectStore('outbox', { keyPath: 'id' })
          store.createIndex('by-sample', 'sampleId')
          store.createIndex('by-status', 'status')
        }
      },
    })
  }
  return dbPromise
}

export interface CachedResult<T> {
  data: T
  cachedAt: number
}

// GET /api/samples always returns every sample visible to the caller (no
// pagination) -- so a fresh fetch replaces the whole cached set rather than
// merging, otherwise a sample that's no longer assigned to this Assistant
// (or was deleted) would linger in the offline view forever.
export async function putCachedSamples(samples: SampleListItem[]): Promise<void> {
  const db = await getDB()
  const tx = db.transaction('samples', 'readwrite')
  const cachedAt = Date.now()
  await tx.store.clear()
  await Promise.all(samples.map((s) => tx.store.put({ ...s, _cachedAt: cachedAt })))
  await tx.done
}

export async function getCachedSamples(): Promise<CachedResult<SampleListItem[]> | null> {
  const db = await getDB()
  const rows = await db.getAll('samples')
  if (rows.length === 0) return null
  const cachedAt = Math.max(...rows.map((r) => r._cachedAt))
  const data = rows.map(({ _cachedAt, ...rest }) => rest)
  return { data, cachedAt }
}

export async function putCachedSampleDetail(detail: SampleDetail): Promise<void> {
  const db = await getDB()
  await db.put('sampleDetail', { ...detail, _cachedAt: Date.now() })
}

export async function getCachedSampleDetail(sampleId: string): Promise<CachedResult<SampleDetail> | null> {
  const db = await getDB()
  const row = await db.get('sampleDetail', sampleId)
  if (!row) return null
  const { _cachedAt, ...data } = row
  return { data, cachedAt: _cachedAt }
}

export async function putCachedImage(key: string, blob: Blob, contentType: string): Promise<void> {
  const db = await getDB()
  await db.put('images', { key, blob, contentType, _cachedAt: Date.now() })
}

export async function getCachedImage(key: string): Promise<{ blob: Blob; contentType: string } | null> {
  const db = await getDB()
  const row = await db.get('images', key)
  if (!row) return null
  return { blob: row.blob, contentType: row.contentType }
}

// -- Outbox primitives (phase 3b) -- raw CRUD only; enqueue/coalescing/
// status-transition semantics live in offline/outbox.ts, built on top of these.
export async function putOutboxItem(item: OutboxItem): Promise<void> {
  const db = await getDB()
  await db.put('outbox', item)
}

export async function getOutboxItem(id: string): Promise<OutboxItem | undefined> {
  const db = await getDB()
  return db.get('outbox', id)
}

export async function getAllOutboxItems(): Promise<OutboxItem[]> {
  const db = await getDB()
  return db.getAll('outbox')
}

export async function getOutboxItemsBySample(sampleId: string): Promise<OutboxItem[]> {
  const db = await getDB()
  return db.getAllFromIndex('outbox', 'by-sample', sampleId)
}

export async function deleteOutboxItem(id: string): Promise<void> {
  const db = await getDB()
  await db.delete('outbox', id)
}
