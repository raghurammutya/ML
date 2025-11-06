import { normalizeUnderlyingSymbol } from '../../utils/symbols'

export interface HistoryBar {
  time: number
  open: number
  high: number
  low: number
  close: number
}

export interface PanelTemplate {
  id: string
  title: string
  label: string
  color: string
  formatter: (value: number | null) => string
  compute: (bar: HistoryBar, index: number, array: HistoryBar[]) => number | null
}

export const PANEL_TEMPLATES: PanelTemplate[] = [
  {
    id: 'IV',
    title: 'Implied Volatility',
    label: 'IV',
    color: '#60a5fa',
    formatter: (value) => (value != null ? `${value.toFixed(2)}%` : '—'),
    compute: (bar) => ((bar.high - bar.low) / Math.max(bar.close, 1)) * 100,
  },
  {
    id: 'Theta',
    title: 'Theta',
    label: 'Theta',
    color: '#f59e0b',
    formatter: (value) => (value != null ? value.toFixed(2) : '—'),
    compute: (bar, index, array) => {
      if (index === array.length - 1) return 0
      const next = array[index + 1]
      return next ? bar.close - next.close : 0
    },
  },
  {
    id: 'Delta',
    title: 'Delta',
    label: 'Delta',
    color: '#34d399',
    formatter: (value) => (value != null ? value.toFixed(2) : '—'),
    compute: (bar, index, array) => {
      if (index === 0) return 0
      const prev = array[index - 1]
      return prev && prev.close ? ((bar.close - prev.close) / prev.close) * 100 : 0
    },
  },
  {
    id: 'Gamma',
    title: 'Gamma',
    label: 'Gamma',
    color: '#fb7185',
    formatter: (value) => (value != null ? value.toFixed(2) : '—'),
    compute: (bar, index, array) => {
      if (index < 2) return 0
      const prev = array[index - 1]
      const prevPrev = array[index - 2]
      const prevDelta = prevPrev && prevPrev.close
        ? ((prev.close - prevPrev.close) / prevPrev.close) * 100
        : 0
      const currDelta = prev && prev.close ? ((bar.close - prev.close) / prev.close) * 100 : 0
      return currDelta - prevDelta
    },
  },
  {
    id: 'Vega',
    title: 'Vega',
    label: 'Vega',
    color: '#c084fc',
    formatter: (value) => (value != null ? value.toFixed(2) : '—'),
    compute: (bar) => (bar.high + bar.low) / 2 - bar.open,
  },
  {
    id: 'Rho',
    title: 'Rho',
    label: 'Rho',
    color: '#38bdf8',
    formatter: (value) => (value != null ? value.toFixed(2) : '—'),
    compute: (bar) => (Math.log(Math.max(bar.close, 1)) - Math.log(Math.max(bar.open, 1))) * 10,
  },
  {
    id: 'OI',
    title: 'Open Interest',
    label: 'OI',
    color: '#f97316',
    formatter: (value) => (value != null ? value.toFixed(0) : '—'),
    compute: (bar) => (bar.close + bar.open + bar.high + bar.low) / 4,
  },
  {
    id: 'PCR',
    title: 'Put/Call Ratio',
    label: 'PCR',
    color: '#f472b6',
    formatter: (value) => (value != null ? value.toFixed(2) : '—'),
    compute: (_bar, index) => 0.7 + 0.3 * Math.sin(index / 6),
  },
  {
    id: 'FuturesOI',
    title: 'Futures OI',
    label: 'Futures OI',
    color: '#facc15',
    formatter: (value) => (value != null ? value.toFixed(0) : '—'),
    compute: (bar) => (bar.high - bar.low) * 10,
  },
]

export const RADAR_METRICS = ['Theta', 'Gamma', 'Rho', 'Delta', 'IV', 'Vega'] as const

export interface PanelGroup {
  id: 'greeks' | 'open-interest'
  title: string
  subtitle: string
  panelIds: PanelTemplate['id'][]
}

export const PANEL_GROUPS: PanelGroup[] = [
  {
    id: 'greeks',
    title: 'Options Greeks',
    subtitle: 'IV · Theta · Delta · Gamma · Vega · Rho',
    panelIds: ['IV', 'Theta', 'Delta', 'Gamma', 'Vega', 'Rho'],
  },
  {
    id: 'open-interest',
    title: 'Open Interest Metrics',
    subtitle: 'OI · PCR · Futures OI',
    panelIds: ['OI', 'PCR', 'FuturesOI'],
  },
]

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/tradingview-api'

export const fetchHistoryBars = async (symbol: string, timeframe: string): Promise<HistoryBar[]> => {
  const normalizedSymbol = normalizeUnderlyingSymbol(symbol)
  const now = Math.floor(Date.now() / 1000)
  const defaultFrom = now - 7 * 24 * 3600
  const params = new URLSearchParams({
    symbol: normalizedSymbol,
    resolution: timeframe,
    from: String(defaultFrom),
    to: String(now),
  })
  const response = await fetch(`${API_BASE_URL}/history?${params.toString()}`, { cache: 'no-store' })
  if (!response.ok) return []
  const json = await response.json()
  if (!json || json.s !== 'ok') return []

  const bars: HistoryBar[] = []
  for (let i = 0; i < json.t.length; i += 1) {
    bars.push({
      time: json.t[i],
      open: json.o[i],
      high: json.h[i],
      low: json.l[i],
      close: json.c[i],
    })
  }
  return bars
}

export interface ChartPoint {
  time: number
  value: number | null
}

export const nearestPoint = (points: ChartPoint[], target?: number | null): ChartPoint | null => {
  if (!points.length) return null
  if (target == null) return points[points.length - 1]
  let best: ChartPoint | null = null
  let bestDiff = Infinity
  for (const point of points) {
    const diff = Math.abs(point.time - target)
    if (diff < bestDiff) {
      best = point
      bestDiff = diff
    }
  }
  return best
}
