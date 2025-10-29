export interface HealthStatus {
  status: string
  database: string
  redis: string
  cache_stats: CacheStats
  uptime: number
  version: string
}

export interface CacheStats {
  l1_hits: number
  l2_hits: number
  l3_hits: number
  total_misses: number
  hit_rate: number
  memory_cache_size: number
  redis_keys: number
}

export interface LabelDistribution {
  timeframe: string
  period_days: number
  distribution: Record<string, number>
}

export interface ChartMark {
  id: string
  time: number
  color: string
  text: string
  label: string
  labelFontColor: string
  minSize: number
}

export interface HistoryData {
  s: string
  t?: number[]
  o?: number[]
  h?: number[]
  l?: number[]
  c?: number[]
  v?: number[]
  errmsg?: string
}

export const LABEL_COLORS: Record<string, string> = {
  'Very Bearish': '#8B0000',
  'Bearish': '#FF0000',
  'Somewhat Bearish': '#FF6347',
  'Neutral': '#808080',
  'Somewhat Bullish': '#90EE90',
  'Bullish': '#00FF00',
  'Very Bullish': '#006400'
}

export type FoOrientation = 'horizontal' | 'vertical'
export type FoIndicatorId = 'iv' | 'delta' | 'gamma' | 'theta' | 'vega' | 'oi' | 'pcr' | 'max_pain'

export interface FoIndicatorDefinition {
  id: string
  label: string
  indicator: FoIndicatorId | string
  orientation: FoOrientation
  option_side?: 'call' | 'put' | 'both'
  default: boolean
}

export interface FoMoneynessPoint {
  time: number
  value: number
}

export interface FoMoneynessSeries {
  expiry: string
  bucket: string
  points: FoMoneynessPoint[]
}

export interface FoMoneynessSeriesResponse {
  status: string
  symbol: string
  timeframe: string
  indicator: string
  series: FoMoneynessSeries[]
}

export interface FoStrikePoint {
  strike: number
  value: number
  call?: number | null
  put?: number | null
  call_oi?: number | null
  put_oi?: number | null
  bucket_time?: number
  underlying?: number | null
}

export interface FoStrikeSeries {
  expiry: string
  bucket_time: number | null
  points: FoStrikePoint[]
}

export interface FoStrikeDistributionResponse {
  status: string
  symbol: string
  timeframe: string
  indicator: string
  series: FoStrikeSeries[]
}

export interface FoExpiriesResponse {
  status: string
  symbol: string
  expiries: string[]
}

export interface FoRealtimeStrike {
  strike: number
  call: {
    iv: number | null
    delta: number | null
    gamma: number | null
    theta: number | null
    vega: number | null
    volume: number | null
    oi: number | null
  }
  put: {
    iv: number | null
    delta: number | null
    gamma: number | null
    theta: number | null
    vega: number | null
    volume: number | null
    oi: number | null
  }
  underlying?: number | null
}

export interface FoRealtimeMetrics {
  bucket_time: number
  timeframe: string
  symbol: string
  expiry: string
  total_call_volume?: number
  total_put_volume?: number
  total_call_oi?: number
  total_put_oi?: number
  pcr?: number | null
  max_pain_strike?: number | null
}

export interface FoRealtimeBucket {
  type: 'fo_bucket'
  timeframe: string
  symbol: string
  expiry: string
  bucket_time: number
  strikes: {
    strike: number
    call: { iv: number | null; delta: number | null; gamma: number | null; theta: number | null; vega: number | null; volume: number | null; oi: number | null }
    put: { iv: number | null; delta: number | null; gamma: number | null; theta: number | null; vega: number | null; volume: number | null; oi: number | null }
    underlying?: number | null
  }[]
  metrics: FoRealtimeMetrics
}

export interface MonitorInstrument {
  instrument_token: number
  tradingsymbol: string
  name?: string | null
  segment?: string | null
  instrument_type?: string | null
  exchange?: string | null
  lot_size?: number | null
  tick_size?: number | null
  last_price?: number | null
  last_price_ts?: string | null
}

export interface MonitorOptionLeg {
  instrument_token: number
  tradingsymbol: string
  segment?: string | null
  exchange?: string | null
  lot_size?: number | null
  tick_size?: number | null
}

export interface MonitorOptionStrike {
  strike: number
  call: MonitorOptionLeg | null
  put: MonitorOptionLeg | null
}

export interface MonitorOptionExpiry {
  expiry: string
  atm_strike: number | null
  strikes: MonitorOptionStrike[]
}

export interface MonitorMetadataResponse {
  status: string
  symbol: string
  underlying?: MonitorInstrument | null
  futures: MonitorOptionLeg[]
  options: MonitorOptionExpiry[]
  meta: {
    otm_levels: number
    expiry_limit: number
    strike_gap: number
    redis_channels: {
      options: string
      underlying: string
    }
  }
}

export interface MonitorSearchResult {
  canonical_symbol: string
  display_symbol: string
  name: string | null
  segment: string | null
  instrument_type: string | null
  exchange: string | null
  instrument_token?: number | null
}

export interface MonitorSearchResponse {
  status: string
  results: MonitorSearchResult[]
}

export interface MonitorSessionRequest {
  tokens: number[]
  requested_mode?: string | null
  account_id?: string | null
}

export interface MonitorSessionResponse {
  status: string
  session_id: string
  tokens: number[]
}

export interface MonitorSessionDeleteResponse {
  status: string
  session_id: string
  released: number[]
}

export interface MonitorSnapshotResponse {
  status: string
  underlying: Record<string, unknown> | null
  options: Record<string, Record<string, unknown>>
}

export interface MonitorStreamMessage {
  channel: string
  payload: Record<string, unknown>
}
