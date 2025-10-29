import { api } from './api'
import type {
  MonitorMetadataResponse,
  MonitorSessionRequest,
  MonitorSessionResponse,
  MonitorSessionDeleteResponse,
  MonitorSnapshotResponse,
  MonitorSearchResponse,
  MonitorSearchResult,
} from '../types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/tradingview-api'

export const fetchMonitorMetadata = async (
  params?: { symbol?: string; expiry_limit?: number; otm_levels?: number }
): Promise<MonitorMetadataResponse> => {
  const response = await api.get<MonitorMetadataResponse>('/monitor/metadata', {
    params: {
      symbol: params?.symbol,
      expiry_limit: params?.expiry_limit,
      otm_levels: params?.otm_levels,
    }
  })
  return response.data
}

export const createMonitorSession = async (
  request: MonitorSessionRequest
): Promise<MonitorSessionResponse> => {
  const response = await api.post<MonitorSessionResponse>('/monitor/session', request)
  return response.data
}

export const deleteMonitorSession = async (
  sessionId: string
): Promise<MonitorSessionDeleteResponse> => {
  const response = await api.delete<MonitorSessionDeleteResponse>(`/monitor/session/${sessionId}`)
  return response.data
}

export const fetchMonitorSnapshot = async (): Promise<MonitorSnapshotResponse> => {
  const response = await api.get<MonitorSnapshotResponse>('/monitor/snapshot')
  return response.data
}

export const searchMonitorSymbols = async (
  query: string,
  limit = 20,
  signal?: AbortSignal
): Promise<MonitorSearchResult[]> => {
  const trimmed = query.trim()
  if (!trimmed) return []
  const response = await api.get<MonitorSearchResponse>('/monitor/search', {
    params: { query: trimmed, limit },
    signal,
  })
  return response.data.results
}

const buildWsUrl = (): string => {
  const base = API_BASE_URL
  const isAbsolute = base.startsWith('http://') || base.startsWith('https://')
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  if (isAbsolute) {
    const url = new URL(base)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    url.pathname = `${url.pathname.replace(/\/$/, '')}/monitor/stream`
    return url.toString()
  }
  return `${protocol}//${window.location.host}${base.replace(/\/$/, '')}/monitor/stream`
}

export const connectMonitorStream = (): WebSocket => {
  const wsUrl = buildWsUrl()
  return new WebSocket(wsUrl)
}
