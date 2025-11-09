import { Strategy, StrategyInstrument, M2MCandle } from '../types/strategy'

const BACKEND_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8081'

const authHeaders = (jwtToken: string, extra?: Record<string, string>) => ({
  Authorization: `Bearer ${jwtToken}`,
  'Content-Type': 'application/json',
  ...extra,
})

const handleResponse = async <T>(response: Response): Promise<T> => {
  if (!response.ok) {
    const detail = await response
      .json()
      .catch(() => ({ detail: `Request failed with status ${response.status}` }))
    throw new Error(detail.detail || 'Request failed')
  }
  return response.json() as Promise<T>
}

export interface CreateStrategyRequest {
  name: string
  description?: string
  tags?: string[]
}

export interface AddInstrumentRequest {
  tradingsymbol: string
  direction: 'BUY' | 'SELL'
  quantity: number
  entry_price: number
  notes?: string
}

export const fetchStrategies = async (jwtToken: string, accountId: string): Promise<Strategy[]> => {
  const response = await fetch(`${BACKEND_URL}/strategies?account_id=${accountId}`, {
    headers: authHeaders(jwtToken),
  })
  return handleResponse<Strategy[]>(response)
}

export const createStrategy = async (
  jwtToken: string,
  accountId: string,
  data: CreateStrategyRequest,
): Promise<Strategy> => {
  const response = await fetch(`${BACKEND_URL}/strategies?account_id=${accountId}`, {
    method: 'POST',
    headers: authHeaders(jwtToken),
    body: JSON.stringify(data),
  })
  return handleResponse<Strategy>(response)
}

export const fetchStrategyDetails = async (
  jwtToken: string,
  accountId: string,
  strategyId: number,
): Promise<Strategy> => {
  const response = await fetch(`${BACKEND_URL}/strategies/${strategyId}?account_id=${accountId}`, {
    headers: authHeaders(jwtToken),
  })
  return handleResponse<Strategy>(response)
}

export const fetchStrategyInstruments = async (
  jwtToken: string,
  strategyId: number,
): Promise<StrategyInstrument[]> => {
  const response = await fetch(`${BACKEND_URL}/strategies/${strategyId}/instruments`, {
    headers: authHeaders(jwtToken),
  })
  return handleResponse<StrategyInstrument[]>(response)
}

export const addStrategyInstrument = async (
  jwtToken: string,
  strategyId: number,
  payload: AddInstrumentRequest,
): Promise<StrategyInstrument> => {
  const response = await fetch(`${BACKEND_URL}/strategies/${strategyId}/instruments`, {
    method: 'POST',
    headers: authHeaders(jwtToken),
    body: JSON.stringify(payload),
  })
  return handleResponse<StrategyInstrument>(response)
}

export const deleteStrategyInstrument = async (
  jwtToken: string,
  strategyId: number,
  instrumentId: number,
): Promise<void> => {
  const response = await fetch(`${BACKEND_URL}/strategies/${strategyId}/instruments/${instrumentId}`, {
    method: 'DELETE',
    headers: authHeaders(jwtToken),
  })
  if (!response.ok) {
    const detail = await response
      .json()
      .catch(() => ({ detail: `Failed with status ${response.status}` }))
    throw new Error(detail.detail || 'Failed to delete instrument')
  }
}

export const fetchStrategyM2M = async (
  jwtToken: string,
  strategyId: number,
  fromTime: number,
  toTime: number,
): Promise<M2MCandle[]> => {
  const params = new URLSearchParams({
    from_time: String(fromTime),
    to_time: String(toTime),
  })
  const response = await fetch(`${BACKEND_URL}/strategies/${strategyId}/m2m?${params.toString()}`, {
    headers: authHeaders(jwtToken),
  })
  return handleResponse<M2MCandle[]>(response)
}
