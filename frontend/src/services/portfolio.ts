/**
 * Portfolio Service
 *
 * Handles communication with Ticker Service for portfolio data:
 * - Fetch positions (net and day)
 * - Fetch holdings
 * - Fetch margins/funds
 */

const TICKER_SERVICE_URL = import.meta.env.VITE_TICKER_SERVICE_URL || 'http://localhost:8001'

export interface Position {
  tradingsymbol: string
  exchange: string
  product: string
  quantity: number
  overnight_quantity: number
  multiplier: number
  average_price: number
  close_price: number
  last_price: number
  value: number
  pnl: number
  m2m: number
  unrealised: number
  realised: number
  buy_quantity: number
  buy_price: number
  buy_value: number
  buy_m2m: number
  sell_quantity: number
  sell_price: number
  sell_value: number
  sell_m2m: number
  day_buy_quantity: number
  day_buy_price: number
  day_buy_value: number
  day_sell_quantity: number
  day_sell_price: number
  day_sell_value: number
}

export interface PositionsResponse {
  net: Position[]
  day: Position[]
}

export interface Holding {
  tradingsymbol: string
  exchange: string
  isin: string
  quantity: number
  t1_quantity: number
  realised_quantity: number
  authorised_quantity: number
  authorised_date: string
  opening_quantity: number
  collateral_quantity: number
  collateral_type: string
  discrepancy: boolean
  average_price: number
  last_price: number
  close_price: number
  pnl: number
  day_change: number
  day_change_percentage: number
}

export interface MarginSegment {
  enabled: boolean
  net: number
  available: {
    adhoc_margin: number
    cash: number
    opening_balance: number
    live_balance: number
    collateral: number
    intraday_payin: number
  }
  utilised: {
    debits: number
    exposure: number
    m2m_realised: number
    m2m_unrealised: number
    option_premium: number
    payout: number
    span: number
    holding_sales: number
    turnover: number
    liquid_collateral: number
    stock_collateral: number
    delivery: number
  }
}

export interface MarginsResponse {
  equity: MarginSegment
  commodity: MarginSegment
}

/**
 * Fetch positions for a trading account
 * Returns both net and day positions
 */
export const fetchPositions = async (
  jwtToken: string,
  tradingAccountId: number
): Promise<PositionsResponse> => {
  const response = await fetch(`${TICKER_SERVICE_URL}/portfolio/positions`, {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${jwtToken}`,
      'X-Account-ID': String(tradingAccountId),
      'Content-Type': 'application/json'
    }
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to fetch positions' }))
    throw new Error(error.detail || 'Failed to fetch positions')
  }

  return response.json()
}

/**
 * Fetch holdings for a trading account
 * Returns long-term equity holdings
 */
export const fetchHoldings = async (
  jwtToken: string,
  tradingAccountId: number
): Promise<Holding[]> => {
  const response = await fetch(`${TICKER_SERVICE_URL}/portfolio/holdings`, {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${jwtToken}`,
      'X-Account-ID': String(tradingAccountId),
      'Content-Type': 'application/json'
    }
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to fetch holdings' }))
    throw new Error(error.detail || 'Failed to fetch holdings')
  }

  return response.json()
}

/**
 * Fetch margin/funds for a trading account
 * Returns equity and commodity segment margins
 */
export const fetchMargins = async (
  jwtToken: string,
  tradingAccountId: number,
  segment?: 'equity' | 'commodity'
): Promise<MarginsResponse> => {
  const url = new URL(`${TICKER_SERVICE_URL}/account/margins`)
  if (segment) {
    url.searchParams.append('segment', segment)
  }

  const response = await fetch(url.toString(), {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${jwtToken}`,
      'X-Account-ID': String(tradingAccountId),
      'Content-Type': 'application/json'
    }
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to fetch margins' }))
    throw new Error(error.detail || 'Failed to fetch margins')
  }

  return response.json()
}

/**
 * Convert position product type
 */
export const convertPosition = async (
  jwtToken: string,
  tradingAccountId: number,
  params: {
    exchange: string
    tradingsymbol: string
    transaction_type: 'BUY' | 'SELL'
    position_type: 'day' | 'overnight'
    quantity: number
    old_product: 'CNC' | 'NRML' | 'MIS'
    new_product: 'CNC' | 'NRML' | 'MIS'
  }
): Promise<boolean> => {
  const response = await fetch(`${TICKER_SERVICE_URL}/portfolio/positions/convert`, {
    method: 'PUT',
    headers: {
      'Authorization': `Bearer ${jwtToken}`,
      'X-Account-ID': String(tradingAccountId),
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(params)
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to convert position' }))
    throw new Error(error.detail || 'Failed to convert position')
  }

  return response.json()
}

/**
 * Format currency for Indian locale
 */
export const formatINR = (value: number): string => {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(value)
}

/**
 * Format number with Indian locale
 */
export const formatNumber = (value: number, decimals: number = 2): string => {
  return new Intl.NumberFormat('en-IN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  }).format(value)
}

/**
 * Format percentage
 */
export const formatPercentage = (value: number, decimals: number = 2): string => {
  return `${value >= 0 ? '+' : ''}${value.toFixed(decimals)}%`
}
