export interface Strategy {
  strategy_id: number
  name: string
  description: string | null
  tags: string[]
  status: 'active' | 'archived'
  is_default: boolean
  created_at: string
  updated_at: string
  archived_at: string | null
  current_pnl: number
  current_m2m: number
  total_capital_deployed: number
  total_margin_used: number
  instrument_count: number
}

export interface StrategyInstrument {
  id: number
  strategy_id: number
  tradingsymbol: string
  exchange: string
  instrument_type: string
  strike: number | null
  expiry: string | null
  direction: 'BUY' | 'SELL'
  quantity: number
  entry_price: number
  current_price: number | null
  current_pnl: number | null
  added_at: string
  notes: string | null
  lot_size: number
}

export interface M2MCandle {
  timestamp: string
  open: number
  high: number
  low: number
  close: number
}
