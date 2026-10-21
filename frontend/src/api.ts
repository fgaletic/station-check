export type Status = 'ok' | 'warning' | 'alert' | 'unknown'
export type VariableId = 'temperature' | 'humidity' | 'radiation'

export interface VariableHealth {
  variable: VariableId
  label: string
  unit: string
  status: Status
  deviation: number | null
  message?: string
  thresholds?: { warning: number; alert: number }
  stuck?: boolean
  daily?: { day: string; deviation: number }[]
}

export interface Greenhouse {
  id: number
  name: string
  lat: number
  lon: number
  companyId: string
  station: { code: string; name: string; km: number }
  scenario: string
  scenarioLabel: string
  status: Status
  variables: VariableHealth[]
  source: {
    refSensorId: string | null
    healthSensorId: string | null
    syncedUntil: string | null
    lastSyncAt: string | null
    lastSyncError: string | null
  }
  baseline: { start: string; end: string }
}

export interface SeriesPoint { ts: string; farm: number; ref: number }
export interface Company { id: string; name: string }
export interface Scenario { id: string; label: string }
export interface NearestStation { code: string; name: string; comarca: string; km: number; lat: number; lon: number }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const detail = body?.detail
    throw new Error(typeof detail === 'string' ? detail : `Request failed (${res.status})`)
  }
  return (res.status === 204 ? undefined : await res.json()) as T
}

export const api = {
  greenhouses: () => request<Greenhouse[]>('/greenhouses'),
  greenhouse: (id: number) => request<Greenhouse>(`/greenhouses/${id}`),
  series: (id: number, variable: VariableId, days = 14) =>
    request<{ points: SeriesPoint[] }>(`/greenhouses/${id}/series?variable=${variable}&days=${days}`),
  create: (body: { name: string; lat: number; lon: number; companyId: string; scenario: string }) =>
    request<Greenhouse>('/greenhouses', { method: 'POST', body: JSON.stringify(body) }),
  sync: (id: number) =>
    request<{ newReadings: number; sentToSource: number; error: string | null; greenhouse: Greenhouse }>(
      `/greenhouses/${id}/sync`, { method: 'POST' }),
  remove: (id: number) => request<void>(`/greenhouses/${id}`, { method: 'DELETE' }),
  nearestStation: (lat: number, lon: number) => request<NearestStation>(`/stations/nearest?lat=${lat}&lon=${lon}`),
  companies: () => request<Company[]>('/companies'),
  scenarios: () => request<Scenario[]>('/scenarios'),
}

const madrid = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Europe/Madrid', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
})

/** Backend timestamps are UTC; show them in Catalan local time. */
export function formatTime(ts: string | null): string {
  if (!ts) return '–'
  return madrid.format(new Date(ts.endsWith('Z') ? ts : ts + 'Z'))
}

export function formatDeviation(v: VariableHealth): string {
  if (v.deviation === null) return '–'
  const digits = v.unit === '%' ? 0 : 1
  const shown = Number(v.deviation.toFixed(digits))
  const sign = shown > 0 ? '+' : shown < 0 ? '−' : ''
  return `${sign}${Math.abs(shown).toFixed(digits)} ${v.unit}`
}
