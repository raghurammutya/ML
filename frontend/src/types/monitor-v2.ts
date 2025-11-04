// MonitorV2 TypeScript Interfaces

export type Universe = 'NIFTY' | 'BANKNIFTY' | 'FINNIFTY' | 'MIDCPNIFTY' | string

export type Timeframe = '1min' | '5min' | '15min' | '30min' | '1hour' | '1day'

export type IndicatorType = 'iv' | 'delta' | 'gamma' | 'theta' | 'vega' | 'volume' | 'oi' | 'pcr'

export type OptionSide = 'call' | 'put' | 'both'

export type ThemeMode = 'light' | 'dark' | 'auto'

// Account & Trading
export interface TradingAccount {
  id: string
  name: string
  broker: string
  accountType: 'live' | 'paper' | 'backtest'
  balance: number
  isActive: boolean
}

export interface Position {
  id: string
  symbol: string
  expiry: string
  strike: number
  optionType: 'call' | 'put'
  quantity: number
  avgPrice: number
  currentPrice: number
  pnl: number
  pnlPercent: number
}

export interface Order {
  id: string
  symbol: string
  expiry: string
  strike: number
  optionType: 'call' | 'put'
  orderType: 'buy' | 'sell'
  quantity: number
  price: number
  status: 'pending' | 'filled' | 'cancelled' | 'rejected'
  timestamp: number
}

export interface Strategy {
  id: string
  name: string
  description: string
  positions: Position[]
  totalPnl: number
  maxRisk: number
  isActive: boolean
}

// Layout & UI State
export interface UniverseLayout {
  id: string
  name: string
  universe: Universe
  showLeftPanel: boolean
  showRightPanel: boolean
  showRadarCharts: boolean
  leftPanelWidth: number
  rightPanelWidth: number
  chartHeight: number
  bottomTabsHeight: number
  activeTabs: IndicatorType[]
  savedAt: number
}

export interface ReplayState {
  enabled: boolean
  currentTime: number
  startTime: number
  endTime: number
  playbackSpeed: number // 1x, 2x, 5x, 10x
  isPlaying: boolean
  loopEnabled: boolean
}

export interface ChartConfig {
  symbol: string
  timeframe: Timeframe
  showVolume: boolean
  showGrid: boolean
  candleType: 'candle' | 'line' | 'area'
  theme: 'dark' | 'light'
  timezone: string
  autoScale: boolean
}

export interface UniverseFilters {
  selectedExpiries: string[]
  availableExpiries: string[]
  strikeRange: number // ATM ± N strikes
  indicators: IndicatorType[]
  optionSide: OptionSide
  minOI: number
  minVolume: number
}

export interface MetricTabConfig {
  id: string
  indicator: IndicatorType
  label: string
  color: string
  isActive: boolean
  order: number
  showCallPut: boolean
}

export interface SidePanelConfig {
  position: 'left' | 'right'
  activeIndicator: IndicatorType
  showLegend: boolean
  syncWithChart: boolean
  strikeRange: number
}

export interface AccountPanelState {
  selectedAccountId: string | null
  showPositions: boolean
  showOrders: boolean
  showStrategies: boolean
  expandedStrategyId: string | null
}

// Data Models
export interface OHLCBar {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface StrikeData {
  strike: number
  expiry: string
  callIV: number
  putIV: number
  callDelta: number
  putDelta: number
  callGamma: number
  putGamma: number
  callTheta: number
  putTheta: number
  callVega: number
  putVega: number
  callOI: number
  putOI: number
  callVolume: number
  putVolume: number
  underlying: number
}

export interface MoneynessData {
  bucket: string // ATM, ITM1, OTM1, etc.
  value: number
  callValue: number
  putValue: number
  strikeCount: number
}

export interface MetricSeries {
  expiry: string
  data: StrikeData[]
  color: string
}

// User Preferences
export interface UserPreferences {
  theme: ThemeMode
  defaultUniverse: Universe
  defaultTimeframe: Timeframe
  defaultAccount: string
  savedLayouts: UniverseLayout[]
  notifications: {
    enabled: boolean
    sound: boolean
    desktop: boolean
  }
}

// Component Props Types
export interface GlobalHeaderProps {
  user: {
    name: string
    email: string
    avatar?: string
  }
  accounts: TradingAccount[]
  selectedAccountId: string | null
  onAccountSelect: (accountId: string) => void
  activeUniverse: Universe
  universes: Universe[]
  onUniverseChange: (universe: Universe) => void
  onAddUniverse: () => void
  theme: ThemeMode
  onThemeChange: (theme: ThemeMode) => void
  onLogout: () => void
}

export interface ControlPanelProps {
  filters: UniverseFilters
  onFiltersChange: (filters: Partial<UniverseFilters>) => void
  timeframe: Timeframe
  onTimeframeChange: (timeframe: Timeframe) => void
  replayState: ReplayState
  onReplayToggle: () => void
  onSaveLayout: () => void
  onLoadLayout: () => void
  savedLayouts: UniverseLayout[]
}

export interface UnderlyingChartProps {
  symbol: string
  timeframe: Timeframe
  data?: OHLCBar[]
  config: ChartConfig
  onConfigChange: (config: Partial<ChartConfig>) => void
  height: number
  replayTime?: number
}

export interface MetricPanelProps {
  position?: 'left' | 'right'
  config: SidePanelConfig
  series?: MetricSeries[]
  priceRange?: { min: number; max: number }
  onConfigChange: (config: Partial<SidePanelConfig>) => void
  height: number
}

export interface MetricTabsProps {
  tabs: MetricTabConfig[]
  activeTabId: string
  onTabChange: (tabId: string) => void
  series?: MetricSeries[]
  height: number
  expiries: string[]
}

export interface RadarChartProps {
  position?: 'left' | 'right'
  data: {
    metric: string
    value: number
    max: number
  }[]
  height: number
}
