// Trading service - connects to backend /accounts API
import { api } from './api'

const API_BASE = '/accounts'

export interface TradingAccount {
  id: string
  display_name: string
  user_id: string
  combined_pnl: number
  margin_used: number
  available_margin: number
  roi_percent: number
  has_exposure: boolean
}

export interface Order {
  id: string
  trading_account_id: string
  underlying: string
  instrument_type: string
  expiry?: string
  strike?: number
  side: 'BUY' | 'SELL'
  qty: number
  price: number
  status: 'OPEN' | 'COMPLETE' | 'CANCELLED' | 'REJECTED'
  placed_at: string
  filled_qty: number
}

export interface Position {
  id: string
  trading_account_id: string
  underlying: string
  instrument_type: string
  expiry?: string
  strike?: number
  qty: number
  avg_price: number
  pnl_unrealized: number
  pnl_realized: number
  updated_at: string
}

export interface Holding {
  id: string
  trading_account_id: string
  underlying: string
  product_type: string
  qty: number
  avg_cost: number
  market_value: number
  updated_at: string
}

export interface Funds {
  trading_account_id: string
  cash_balance: number
  margin_used: number
  available_margin: number
  updated_at: string
}

export interface ParticipantAccount {
  trading_account_id: string
  display_name: string
  orders_count: number
  positions_count: number
  combined_pnl: number
  margin_used: number
  roi_percent: number
}

// Helper function to map backend account response to frontend TradingAccount
function mapBackendAccount(backendAccount: any): TradingAccount {
  const margin_used = backendAccount.total_pnl < 0 ? Math.abs(backendAccount.total_pnl) : 0
  const roi_percent = margin_used > 0 ? (backendAccount.total_pnl / margin_used) * 100 : 0

  return {
    id: backendAccount.account_id,
    display_name: backendAccount.account_name,
    user_id: backendAccount.account_id,
    combined_pnl: backendAccount.total_pnl || 0,
    margin_used: margin_used,
    available_margin: backendAccount.available_margin || 0,
    roi_percent: roi_percent,
    has_exposure: backendAccount.total_positions > 0
  }
}

// API functions

export const fetchAllAccounts = async (): Promise<TradingAccount[]> => {
  try {
    const response = await api.get(API_BASE)
    const data = response.data

    if (data.status === 'success' && data.accounts) {
      return data.accounts.map(mapBackendAccount)
    }

    console.error('Failed to fetch accounts:', data)
    return []
  } catch (error) {
    console.error('Error fetching accounts:', error)
    return []
  }
}

export const fetchParticipatingAccounts = async (underlying: string): Promise<ParticipantAccount[]> => {
  try {
    // Fetch all accounts
    const accounts = await fetchAllAccounts()

    // Filter accounts with exposure and fetch their positions to check for underlying
    const participatingAccounts: ParticipantAccount[] = []

    for (const account of accounts) {
      if (!account.has_exposure) continue

      // Fetch positions to check if account has positions in this underlying
      const positions = await fetchAccountPositions(account.id, underlying)
      const orders = await fetchAccountOrders(account.id, underlying)

      if (positions.length > 0 || orders.length > 0) {
        const pnl = positions.reduce((sum, pos) => sum + (pos.pnl_unrealized || 0) + (pos.pnl_realized || 0), 0)

        participatingAccounts.push({
          trading_account_id: account.id,
          display_name: account.display_name,
          orders_count: orders.length,
          positions_count: positions.length,
          combined_pnl: pnl,
          margin_used: account.margin_used,
          roi_percent: account.roi_percent
        })
      }
    }

    return participatingAccounts
  } catch (error) {
    console.error('Error fetching participating accounts:', error)
    return []
  }
}

export const fetchAccountOrders = async (
  accountId: string,
  underlying?: string
): Promise<Order[]> => {
  try {
    const response = await api.get(`${API_BASE}/${accountId}/orders`)
    const data = response.data

    if (data.status === 'success' && data.orders) {
      let orders = data.orders

      // Filter by underlying if provided
      if (underlying) {
        orders = orders.filter((o: any) =>
          o.tradingsymbol?.startsWith(underlying) ||
          o.underlying === underlying
        )
      }

      // Map backend order structure to frontend Order interface
      return orders.map((o: any) => ({
        id: o.order_id || o.id,
        trading_account_id: accountId,
        underlying: o.underlying || extractUnderlyingFromSymbol(o.tradingsymbol),
        instrument_type: o.instrument_type || extractInstrumentType(o.tradingsymbol),
        expiry: o.expiry,
        strike: o.strike,
        side: o.transaction_type === 'BUY' ? 'BUY' : 'SELL',
        qty: o.quantity || 0,
        price: o.price || 0,
        status: mapOrderStatus(o.status),
        placed_at: o.order_timestamp || o.placed_at,
        filled_qty: o.filled_quantity || 0
      }))
    }

    return []
  } catch (error) {
    console.error(`Error fetching orders for account ${accountId}:`, error)
    return []
  }
}

// Helper functions for order mapping
function extractUnderlyingFromSymbol(symbol: string): string {
  if (!symbol) return ''
  // Extract underlying from symbol like "NIFTY2511324500CE"
  if (symbol.startsWith('NIFTY')) return 'NIFTY50'
  if (symbol.startsWith('BANKNIFTY')) return 'BANKNIFTY'
  return symbol.split(/[0-9]/)[0]
}

function extractInstrumentType(symbol: string): string {
  if (!symbol) return ''
  if (symbol.endsWith('CE')) return 'CE'
  if (symbol.endsWith('PE')) return 'PE'
  return 'FUT'
}

function mapOrderStatus(status: string): 'OPEN' | 'COMPLETE' | 'CANCELLED' | 'REJECTED' {
  if (!status) return 'OPEN'
  const s = status.toUpperCase()
  if (s.includes('COMPLETE') || s === 'COMPLETE') return 'COMPLETE'
  if (s.includes('CANCEL')) return 'CANCELLED'
  if (s.includes('REJECT')) return 'REJECTED'
  return 'OPEN'
}

export const fetchAccountPositions = async (
  accountId: string,
  underlying?: string
): Promise<Position[]> => {
  try {
    const response = await api.get(`${API_BASE}/${accountId}/positions`)
    const data = response.data

    if (data.status === 'success' && data.positions) {
      let positions = data.positions

      // Filter by underlying if provided
      if (underlying) {
        positions = positions.filter((p: any) =>
          p.tradingsymbol?.startsWith(underlying) ||
          p.underlying === underlying
        )
      }

      // Map backend position structure to frontend Position interface
      return positions.map((p: any) => ({
        id: p.id || `${accountId}-${p.tradingsymbol}`,
        trading_account_id: accountId,
        underlying: p.underlying || extractUnderlyingFromSymbol(p.tradingsymbol),
        instrument_type: p.instrument_type || extractInstrumentType(p.tradingsymbol),
        expiry: p.expiry,
        strike: p.strike,
        qty: p.quantity || 0,
        avg_price: p.average_price || 0,
        pnl_unrealized: p.pnl || 0,
        pnl_realized: p.realised || 0,
        updated_at: p.last_price_timestamp || new Date().toISOString()
      }))
    }

    return []
  } catch (error) {
    console.error(`Error fetching positions for account ${accountId}:`, error)
    return []
  }
}

export const fetchAccountHoldings = async (
  accountId: string,
  underlying?: string
): Promise<Holding[]> => {
  try {
    const response = await api.get(`${API_BASE}/${accountId}/holdings`)
    const data = response.data

    if (data.status === 'success' && data.holdings) {
      let holdings = data.holdings

      // Filter by underlying if provided
      if (underlying) {
        holdings = holdings.filter((h: any) =>
          h.tradingsymbol?.startsWith(underlying) ||
          h.underlying === underlying
        )
      }

      // Map backend holding structure to frontend Holding interface
      return holdings.map((h: any) => ({
        id: h.id || `${accountId}-${h.tradingsymbol}`,
        trading_account_id: accountId,
        underlying: h.underlying || h.tradingsymbol,
        product_type: h.product || 'CNC',
        qty: h.quantity || 0,
        avg_cost: h.average_price || 0,
        market_value: (h.last_price || 0) * (h.quantity || 0),
        updated_at: h.last_price_timestamp || new Date().toISOString()
      }))
    }

    return []
  } catch (error) {
    console.error(`Error fetching holdings for account ${accountId}:`, error)
    return []
  }
}

export const fetchAccountFunds = async (accountId: string): Promise<Funds> => {
  try {
    const response = await api.get(`${API_BASE}/${accountId}/funds`)
    const data = response.data

    if (data.status === 'success' && data.funds) {
      const funds = data.funds
      return {
        trading_account_id: accountId,
        cash_balance: funds.cash || funds.available?.cash || 0,
        margin_used: funds.used_margin || funds.utilised?.debits || 0,
        available_margin: funds.available_margin || funds.available?.adhoc_margin || 0,
        updated_at: new Date().toISOString()
      }
    }

    // Return default values if no funds data available
    return {
      trading_account_id: accountId,
      cash_balance: 0,
      margin_used: 0,
      available_margin: 0,
      updated_at: new Date().toISOString()
    }
  } catch (error) {
    console.error(`Error fetching funds for account ${accountId}:`, error)
    throw new Error(`Failed to fetch funds for account ${accountId}`)
  }
}

export const cancelAllOrders = async (accountId: string): Promise<void> => {
  // NOTE: Backend endpoint not yet implemented
  // TODO: Backend team needs to implement POST /api/accounts/{accountId}/cancel-all
  console.warn(`Cancel all orders not yet implemented for account ${accountId}`)
  alert('Cancel all orders feature is not yet available. Please cancel orders individually from your broker platform.')
}

export const exportAccountSnapshot = async (accountId: string): Promise<void> => {
  // NOTE: Backend endpoint not yet implemented
  // TODO: Backend team needs to implement GET /api/accounts/{accountId}/export
  console.warn(`Export snapshot not yet implemented for account ${accountId}`)
  alert('Export snapshot feature is coming soon.')
}

// WebSocket connection for live updates
export class TradingWebSocketClient {
  private ws: WebSocket | null = null
  private reconnectTimeout: NodeJS.Timeout | null = null
  private onOrderUpdate: (order: Order) => void
  private onPositionUpdate: (position: Position) => void
  private onFundsUpdate: (funds: Funds) => void

  constructor(
    onOrderUpdate: (order: Order) => void,
    onPositionUpdate: (position: Position) => void,
    onFundsUpdate: (funds: Funds) => void
  ) {
    this.onOrderUpdate = onOrderUpdate
    this.onPositionUpdate = onPositionUpdate
    this.onFundsUpdate = onFundsUpdate
  }

  connect() {
    // NOTE: Backend WebSocket endpoint not yet implemented
    // TODO: Backend team needs to implement WebSocket endpoint for trading updates
    console.warn('[Trading WS] WebSocket endpoint not yet available. Real-time updates disabled.')
    console.info('[Trading WS] Use the refresh button to manually update trading data.')

    // Suppress unused variable warnings until WebSocket is implemented
    void this.onOrderUpdate
    void this.onPositionUpdate
    void this.onFundsUpdate
    void this.scheduleReconnect

    // Don't attempt to connect until backend is ready
    return

    /* When backend is ready, uncomment this:
    const wsUrl = `ws://${window.location.hostname}/tradingview-api/ws/trading`

    try {
      this.ws = new WebSocket(wsUrl)

      this.ws.onopen = () => {
        console.log('[Trading WS] Connected')
      }

      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)

          switch (message.type) {
            case 'order_update':
              this.onOrderUpdate(message.order)
              break
            case 'position_update':
              this.onPositionUpdate(message.position)
              break
            case 'funds_update':
              this.onFundsUpdate(message.funds)
              break
            default:
              console.warn('[Trading WS] Unknown message type:', message.type)
          }
        } catch (err) {
          console.error('[Trading WS] Failed to parse message:', err)
        }
      }

      this.ws.onerror = (error) => {
        console.error('[Trading WS] Error:', error)
      }

      this.ws.onclose = () => {
        console.log('[Trading WS] Disconnected')
        this.scheduleReconnect()
      }
    } catch (err) {
      console.error('[Trading WS] Failed to connect:', err)
      this.scheduleReconnect()
    }
    */
  }

  private scheduleReconnect() {
    if (this.reconnectTimeout) return

    this.reconnectTimeout = setTimeout(() => {
      this.reconnectTimeout = null
      console.log('[Trading WS] Reconnecting...')
      this.connect()
    }, 3000)
  }

  disconnect() {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout)
      this.reconnectTimeout = null
    }

    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }
}
