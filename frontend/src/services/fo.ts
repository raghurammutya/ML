import { api } from './api'
import type {
  FoIndicatorDefinition,
  FoMoneynessSeriesResponse,
  FoStrikeDistributionResponse,
  FoExpiriesResponse,
  FoRealtimeBucket,
} from '../types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/tradingview-api'

/**
 * Normalize symbol for FO endpoints
 * Backend database stores options data under "NIFTY" while main chart uses "NIFTY50"
 */
const normalizeFoSymbol = (symbol: string): string => {
  if (symbol === 'NIFTY50') {
    return 'NIFTY'
  }
  return symbol
}

export const fetchFoIndicators = async (): Promise<FoIndicatorDefinition[]> => {
  const response = await api.get<{ status: string; indicators: FoIndicatorDefinition[] }>('/fo/indicators')
  return response.data.indicators
}

export const fetchFoExpiries = async (symbol: string): Promise<FoExpiriesResponse> => {
  const normalizedSymbol = normalizeFoSymbol(symbol)
  const response = await api.get<FoExpiriesResponse>('/fo/expiries', { params: { symbol: normalizedSymbol } })
  return response.data
}

export interface MoneynessSeriesParams {
  symbol: string
  timeframe: string
  indicator: string
  option_side?: string
  expiry: string[]
  from?: number
  to?: number
}

export const fetchFoMoneynessSeries = async (params: MoneynessSeriesParams): Promise<FoMoneynessSeriesResponse> => {
  const normalizedSymbol = normalizeFoSymbol(params.symbol)
  const response = await api.get<FoMoneynessSeriesResponse>('/fo/moneyness-series', {
    params: {
      symbol: normalizedSymbol,
      timeframe: params.timeframe,
      indicator: params.indicator,
      option_side: params.option_side,
      expiry: params.expiry,
      from: params.from,
      to: params.to,
    }
  })
  return response.data
}

export interface StrikeDistributionParams {
  symbol: string
  timeframe: string
  indicator: string
  expiry: string[]
  bucket_time?: number
}

export const fetchFoStrikeDistribution = async (params: StrikeDistributionParams): Promise<FoStrikeDistributionResponse> => {
  const normalizedSymbol = normalizeFoSymbol(params.symbol)
  console.log('[fo.ts] fetchFoStrikeDistribution called:', {
    symbol: normalizedSymbol,
    timeframe: params.timeframe,
    indicator: params.indicator,
    expiry: params.expiry
  })
  try {
    const response = await api.get<FoStrikeDistributionResponse>('/fo/strike-distribution', {
      params: {
        symbol: normalizedSymbol,
        timeframe: params.timeframe,
        indicator: params.indicator,
        expiry: params.expiry,
        bucket_time: params.bucket_time,
      }
    })
    console.log('[fo.ts] fetchFoStrikeDistribution response:', response.data)
    return response.data
  } catch (error) {
    console.error('[fo.ts] fetchFoStrikeDistribution error:', error)
    throw error
  }
}

const buildWsUrl = (): string => {
  const base = API_BASE_URL
  const isAbsolute = base.startsWith('http://') || base.startsWith('https://')
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  if (isAbsolute) {
    const url = new URL(base)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    url.pathname = `${url.pathname.replace(/\/$/, '')}/fo/stream`
    return url.toString()
  }
  return `${protocol}//${window.location.host}${base.replace(/\/$/, '')}/fo/stream`
}

export const connectFoStream = (): WebSocket => {
  const wsUrl = buildWsUrl()
  return new WebSocket(wsUrl)
}

export type FoStreamHandler = (payload: FoRealtimeBucket) => void
