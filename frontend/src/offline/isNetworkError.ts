// A network-level failure (request never reached the server -- offline, DNS
// failure, connection refused) has no `response`. A real HTTP error (401,
// 403, 500) does -- that's the server actively answering, and must keep
// flowing to the normal error handling (e.g. api/client.ts's 401 interceptor
// calling logout()) rather than being silently treated as "we're offline."
export function isNetworkError(err: unknown): boolean {
  return !!err && typeof err === 'object' && 'isAxiosError' in err && !(err as { response?: unknown }).response
}
