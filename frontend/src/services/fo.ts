import { api } from './api'
import { normalizeUnderlyingSymbol } from '../utils/symbols'
import type {
  FoIndicatorDefinition,
  FoMoneynessSeriesResponse,
  FoStrikeDistributionResponse,
  FoExpiriesResponse,
  FoExpiriesV2Response,
  FoRealtimeBucket,
} from '../types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/tradingview-api'

/**
 * Normalize symbol for FO endpoints
 * Backend database stores options data under "NIFTY" while main chart uses "NIFTY50"
 */
export const normalizeFoSymbol = (symbol: string): string => {
  const normalized = normalizeUnderlyingSymbol(symbol)
  if (normalized === 'NIFTY') {
    return 'NIFTY50'
  }
  return normalized
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

export const fetchFoExpiriesV2 = async (
  symbol: string,
  backfillDays = 30,
): Promise<FoExpiriesV2Response> => {
  const normalizedSymbol = normalizeFoSymbol(symbol)
  const response = await api.get<FoExpiriesV2Response>('/fo/expiries-v2', {
    params: { symbol: normalizedSymbol, backfill_days: backfillDays },
  })
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
      _ts: Date.now(),
    }
  })
  return response.data
}

export interface StrikeDistributionParams {
  symbol: string
  timeframe: string
  indicator: string
  option_side?: string
  expiry: string[]
  bucket_time?: number
}

export const fetchFoStrikeDistribution = async (params: StrikeDistributionParams): Promise<FoStrikeDistributionResponse> => {
  const normalizedSymbol = normalizeFoSymbol(params.symbol)
  try {
    const response = await api.get<FoStrikeDistributionResponse>('/fo/strike-distribution', {
      params: {
        symbol: normalizedSymbol,
        timeframe: params.timeframe,
        indicator: params.indicator,
        option_side: params.option_side,
        expiry: params.expiry,
        bucket_time: params.bucket_time,
        _ts: Date.now(),
      }
    })
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
