import axios from 'axios'

const TOKEN_KEY = 'atx_token'

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

const apiClient = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
  timeout: 20000,
})

// Attach bearer token to every request.
apiClient.interceptors.request.use((config) => {
  const token = tokenStore.get()
  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export const AUTH_UNAUTHORIZED_EVENT = 'auth:unauthorized'

/** Extract a human-readable message from an API error.
 *  FastAPI returns `detail` as a string for HTTPExceptions and as an array of
 *  `{msg, loc}` objects for 422 validation errors. */
export function apiErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string }
    if (typeof first?.msg === 'string') return first.msg.replace(/^Value error,\s*/i, '')
  }
  return fallback
}

// On 401, drop the token and notify the app so auth state clears immediately
// (otherwise protected routes can stay mounted with failing requests).
apiClient.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401) {
      tokenStore.clear()
      window.dispatchEvent(new Event(AUTH_UNAUTHORIZED_EVENT))
    }
    return Promise.reject(error)
  },
)

export interface User {
  id: number
  email: string
  name: string
  created_at: string
}

export interface Course {
  id: number
  name: string
}

export interface Watch {
  id: number
  user_id: number
  label: string
  num_players: number
  num_holes: number
  course_ids: string
  target_days: string
  window_start: string
  window_end: string
  active: boolean
  created_at: string
}

export type WatchInput = Omit<Watch, 'id' | 'user_id' | 'created_at'>

export interface FoundSlot {
  id: number
  watch_id: number
  course_id: number
  course_name?: string
  date: string
  time: string
  open_slots: number
  found_at: string
  notified: boolean
  booking_url: string
}

export interface ScanResult {
  ran: boolean
  in_window: boolean
  dates_scanned: string[]
  total_slots: number
  new_matches: number
  message: string
}

export interface ScanStatus {
  scheduler_running: boolean
  next_run: string | null
  in_window: boolean
  last_scan: {
    at: string | null
    ran: boolean
    in_window: boolean
    message: string
    dates_scanned: string[]
    total_slots: number
    new_matches: number
    scoped: boolean
  }
}

export const api = {
  // Auth
  signup: (data: { name: string; email: string; password: string }) =>
    apiClient.post<{ access_token: string; token_type: string }>('/auth/signup', data),
  login: (data: { email: string; password: string }) =>
    apiClient.post<{ access_token: string; token_type: string }>('/auth/login', data),
  me: () => apiClient.get<User>('/auth/me'),

  // Reference data
  getCourses: () => apiClient.get<Course[]>('/courses'),

  // Watches
  getWatches: () => apiClient.get<Watch[]>('/watches'),
  createWatch: (data: WatchInput) => apiClient.post<Watch>('/watches', data),
  updateWatch: (id: number, data: Partial<WatchInput>) =>
    apiClient.put<Watch>(`/watches/${id}`, data),
  deleteWatch: (id: number) => apiClient.delete(`/watches/${id}`),

  // Found slots + scanning
  getFoundSlots: (limit = 50) =>
    apiClient.get<FoundSlot[]>('/found-slots', { params: { limit } }),
  scanNow: () => apiClient.post<ScanResult>('/watches/scan-now'),
  getScanStatus: () => apiClient.get<ScanStatus>('/scan-status'),
}
