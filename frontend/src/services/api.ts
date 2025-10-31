import axios from 'axios'
import { HealthStatus, CacheStats, LabelDistribution } from '../types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/tradingview-api'

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000, // 2 minutes for slow session establishment
  headers: {
    'Content-Type': 'application/json'
  }
})

export const fetchHealth = async (): Promise<HealthStatus> => {
  const response = await api.get<HealthStatus>('/health')
  return response.data
}

export const fetchCacheStats = async (): Promise<CacheStats> => {
  const response = await api.get<CacheStats>('/cache/stats')
  return response.data
}

export const fetchLabelDistribution = async (
  timeframe: string,
  days: number
): Promise<LabelDistribution> => {
  const response = await api.get<LabelDistribution>('/api/label-distribution', {
    params: { timeframe, days }
  })
  return response.data
}

const DEFAULT_SYMBOL = (import.meta.env.VITE_CHART_SYMBOL as string | undefined) ?? 'NIFTY50'
const DEFAULT_MONITOR_SYMBOL = (import.meta.env.VITE_MONITOR_SYMBOL as string | undefined) ?? 'NIFTY50'

export const testEndpoints = async () => {
  try {
    const symbolParam = encodeURIComponent(DEFAULT_SYMBOL)
    const searchParam = encodeURIComponent(DEFAULT_MONITOR_SYMBOL)
    const endpoints = [
      '/config',
      `/symbols?symbol=${symbolParam}`,
      `/search?query=${searchParam}`,
      '/time'
    ]
    
    const results = await Promise.all(
      endpoints.map(endpoint => 
        api.get(endpoint).then(res => ({
          endpoint,
          status: 'ok',
          data: res.data
        })).catch(err => ({
          endpoint,
          status: 'error',
          error: err.message
        }))
      )
    )
    
    return results
  } catch (error) {
    console.error('Error testing endpoints:', error)
    return []
  }
}
