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