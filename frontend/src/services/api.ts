import axios from 'axios'
import { HealthStatus, CacheStats, LabelDistribution } from '../types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '../tradingview-api'

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
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

export const testEndpoints = async () => {
  try {
    const endpoints = [
      '/config',
      '/symbols?symbol=NIFTY50',
      '/search?query=NIFTY',
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