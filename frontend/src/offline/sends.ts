import type { AxiosResponse } from 'axios'
import { api } from '../api/client'

// The exact API calls for the four queueable mutation kinds -- defined once
// here and used both for the immediate live attempt (via queueOrSend.ts) and
// for replaying a queued item (via syncEngine.ts). Keeping this in one place
// means the two paths can never silently drift apart (e.g. one sending a
// header the other forgot).

export function sendProfile(sampleId: string, payload: unknown): Promise<AxiosResponse> {
  return api.post(`/samples/${sampleId}/profile`, payload)
}

function imageForm(blob: Blob, filename: string): FormData {
  const form = new FormData()
  form.append('file', new File([blob], filename, { type: blob.type || 'image/jpeg' }))
  return form
}

export function sendMarkingImage(sampleId: string, blob: Blob, filename: string): Promise<AxiosResponse> {
  return api.post(`/samples/${sampleId}/marking-image`, imageForm(blob, filename), {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function sendDiagramImage(sampleId: string, blob: Blob, filename: string): Promise<AxiosResponse> {
  return api.post(`/samples/${sampleId}/diagram-image`, imageForm(blob, filename), {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

// `clientRequestId` is always the outbox item's own `id` -- see
// outbox.ts/syncEngine.ts. The backend (phase 3a) uses it to make a replay
// of the exact same submission safe.
export function sendTestSubmit(
  sampleId: string, assignedTestId: string, rawValues: Record<string, unknown>, clientRequestId: string,
): Promise<AxiosResponse> {
  return api.post(`/samples/${sampleId}/tests/${assignedTestId}/submit`, {
    raw_values: rawValues, client_request_id: clientRequestId,
  })
}
