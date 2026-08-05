import axios from 'axios'
import { useAuthStore } from '../state/authStore'

export const api = axios.create({
  baseURL: '/api',
})

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err?.response?.status === 401) {
      useAuthStore.getState().logout()
    }
    return Promise.reject(err)
  },
)

// FastAPI's error body shape depends on the failure kind: a plain string
// for HTTPException(...), but an ARRAY of {type,loc,msg,input} objects for
// Pydantic 422 validation errors. Handing that array straight to a React
// child (e.g. a notification's `message` prop) throws "objects are not
// valid as a React child" and crashes the whole app -- always route
// unknown-shaped `detail` through this before rendering it.
export function extractErrorMessage(err: unknown, fallback = 'Unknown error'): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        if (d && typeof d === 'object' && 'msg' in d) {
          const loc = Array.isArray((d as { loc?: unknown[] }).loc) ? (d as { loc: unknown[] }).loc.join('.') : ''
          return loc ? `${loc}: ${(d as { msg: string }).msg}` : String((d as { msg: string }).msg)
        }
        return String(d)
      })
      .join('; ')
  }
  return fallback
}
