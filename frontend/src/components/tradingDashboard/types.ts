export type Timeframe =
  | '1min'
  | '2min'
  | '3min'
  | '5min'
  | '15min'
  | '30min'
  | '1hr'
  | '1day'

export interface UserMenuDropdownProps {
  userName?: string
  userEmail?: string
  userAvatar?: string
  onThemeToggle?: () => void
  onLogout?: () => void
}

export interface UniverseTabsBarProps {
  tabs: string[]
  activeTab: string
  onTabClick: (symbol: string) => void
  onCloseTab: (symbol: string) => void
  onAddTabs: (symbols: string[]) => void
  availableSymbols?: string[]
  onSearchSymbols?: (query: string) => Promise<string[]>
}

export interface SymbolSearchBarProps {
  availableSymbols?: string[]
  onAddSymbols: (symbols: string[]) => void
  placeholder?: string
  onSearchSymbols?: (query: string) => Promise<string[]>
}

export interface ReplayToggleSwitchProps {
  enabled: boolean
  onToggle: (enabled: boolean) => void
  speed?: number
  onSpeedChange?: (speed: number) => void
}

export interface ChartControlPanelProps {
  onSaveLayout?: () => void
  onLoadLayout?: () => void
  replayEnabled: boolean
  onReplayToggle: (enabled: boolean) => void
  replaySpeed?: number
  onReplaySpeedChange?: (speed: number) => void
  timeframe: Timeframe
  onTimeframeChange: (timeframe: Timeframe) => void
  selectedIndicators: string[]
  onIndicatorsChange: (indicators: string[]) => void
  alertCount?: number
  messageCount?: number
  onAlertsClick?: () => void
  onMessagesClick?: () => void
  indicatorOptions?: IndicatorOption[]
  expiryOptions?: MultiSelectOption[]
  selectedExpiries?: string[]
  onExpiriesChange?: (values: string[]) => void
  moneynessOptions?: MultiSelectOption[]
  selectedMoneyness?: string[]
  onMoneynessChange?: (values: string[]) => void
}

export interface NotificationIconProps {
  count?: number
  onClick?: () => void
}

export interface TopControlPanelProps {
  tabs: string[]
  activeTab: string
  onTabClick: (symbol: string) => void
  onCloseTab: (symbol: string) => void
  onAddTabs: (symbols: string[]) => void
  replayEnabled: boolean
  onReplayToggle: (enabled: boolean) => void
  replaySpeed?: number
  onReplaySpeedChange?: (speed: number) => void
  timeframe: Timeframe
  onTimeframeChange: (timeframe: Timeframe) => void
  selectedIndicators: string[]
  onIndicatorsChange: (indicators: string[]) => void
  alertCount?: number
  messageCount?: number
  onSaveLayout?: () => void
  onLoadLayout?: () => void
  onAlertsClick?: () => void
  onMessagesClick?: () => void
  availableSymbols?: string[]
  onSearchSymbols?: (query: string) => Promise<string[]>
  indicatorOptions?: IndicatorOption[]
  expiryOptions?: MultiSelectOption[]
  selectedExpiries?: string[]
  onExpiriesChange?: (values: string[]) => void
  moneynessOptions?: MultiSelectOption[]
  selectedMoneyness?: string[]
  onMoneynessChange?: (values: string[]) => void
}

export interface TradingDashboardState {
  tabs: string[]
  activeTab: string
  replayEnabled: boolean
  replaySpeed: number
  timeframe: Timeframe
  selectedIndicators: string[]
  alertCount: number
  messageCount: number
}

export const MOCK_SYMBOL_LIST: string[] = [
  'NIFTY',
  'BANKNIFTY',
  'FINNIFTY',
  'MIDCPNIFTY',
  'RELIANCE',
  'TCS',
  'INFY',
  'HDFC',
  'ICICI',
  'SBIN',
  'ITC',
  'BHARTIARTL',
  'HDFCBANK',
  'KOTAKBANK',
  'LT',
  'AXISBANK',
  'MARUTI',
  'WIPRO',
  'TATASTEEL',
  'ONGC',
]

export interface IndicatorOption {
  value: string
  label: string
}

export interface SymbolFilterState {
  selectedExpiries: string[]
  selectedMoneyness: string[]
  rightExpiry: string | null
}

export const MOCK_INDICATOR_OPTIONS: IndicatorOption[] = [
  { value: 'rsi', label: 'RSI' },
  { value: 'macd', label: 'MACD' },
  { value: 'bb', label: 'Bollinger Bands' },
  { value: 'sma', label: 'SMA' },
  { value: 'ema', label: 'EMA' },
  { value: 'vwap', label: 'VWAP' },
  { value: 'stoch', label: 'Stochastic' },
  { value: 'atr', label: 'ATR' },
]
import type { MultiSelectOption } from '../common/MultiSelectDropdown'
