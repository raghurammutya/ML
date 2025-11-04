import React, { useState } from 'react'
import type {
  TradingAccount,
  Universe,
  UniverseLayout,
  UniverseFilters,
  ChartConfig,
  ReplayState,
  ThemeMode,
  Timeframe,
} from '../types/monitor-v2'
import { GlobalHeader } from '../components/monitor-v2/GlobalHeader'
import { ControlPanel } from '../components/monitor-v2/ControlPanel'
import { UniversePage } from '../components/monitor-v2/UniversePage'

// Mock Data
const MOCK_USER = {
  name: 'John Trader',
  email: 'john@trading.com',
}

const MOCK_ACCOUNTS: TradingAccount[] = [
  {
    id: 'acc1',
    name: 'Live',
    broker: 'Zerodha',
    accountType: 'live',
    balance: 500000,
    isActive: true,
  },
  {
    id: 'acc2',
    name: 'Paper',
    broker: 'Zerodha',
    accountType: 'paper',
    balance: 1000000,
    isActive: false,
  },
]

const MOCK_UNIVERSES: Universe[] = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY']

const MOCK_EXPIRIES = ['2025-11-04', '2025-11-11', '2025-11-18', '2025-11-28']

const MonitorV2: React.FC = () => {
  // Global State
  const [theme, setTheme] = useState<ThemeMode>('dark')
  const [selectedAccountId, setSelectedAccountId] = useState<string>('acc1')
  const [activeUniverse, setActiveUniverse] = useState<Universe>('NIFTY')
  const [timeframe, setTimeframe] = useState<Timeframe>('5min')

  // Universe-specific state
  const [currentLayout, setCurrentLayout] = useState<UniverseLayout>({
    id: 'default',
    name: 'Default Layout',
    universe: 'NIFTY',
    showLeftPanel: true,
    showRightPanel: true,
    showRadarCharts: true,
    leftPanelWidth: 280,
    rightPanelWidth: 280,
    chartHeight: 500,
    bottomTabsHeight: 300,
    activeTabs: ['theta', 'gamma', 'delta', 'iv', 'vega', 'oi'],
    savedAt: Date.now(),
  })

  const [filters, setFilters] = useState<UniverseFilters>({
    selectedExpiries: ['2025-11-04', '2025-11-11', '2025-11-18'],
    availableExpiries: MOCK_EXPIRIES,
    strikeRange: 10,
    indicators: ['iv', 'delta', 'gamma', 'theta', 'vega', 'oi'],
    optionSide: 'both',
    minOI: 0,
    minVolume: 0,
  })

  const [chartConfig, setChartConfig] = useState<ChartConfig>({
    symbol: activeUniverse,
    timeframe: timeframe,
    showVolume: true,
    showGrid: true,
    candleType: 'candle',
    theme: 'dark',
    timezone: 'Asia/Kolkata',
    autoScale: true,
  })

  const [replayState, setReplayState] = useState<ReplayState>({
    enabled: false,
    currentTime: Date.now(),
    startTime: Date.now() - 6 * 60 * 60 * 1000, // 6 hours ago
    endTime: Date.now(),
    playbackSpeed: 1,
    isPlaying: false,
    loopEnabled: false,
  })

  const [savedLayouts, setSavedLayouts] = useState<UniverseLayout[]>([])

  // Handlers
  const handleUniverseChange = (universe: Universe) => {
    setActiveUniverse(universe)
    setChartConfig({ ...chartConfig, symbol: universe })
    setCurrentLayout({ ...currentLayout, universe })
  }

  const handleAddUniverse = () => {
    const newUniverse = prompt('Enter universe symbol (e.g., RELIANCE)')
    if (newUniverse) {
      // Would add to universes list
      console.log('Add universe:', newUniverse)
    }
  }

  const handleFiltersChange = (updates: Partial<UniverseFilters>) => {
    setFilters({ ...filters, ...updates })
  }

  const handleTimeframeChange = (newTimeframe: Timeframe) => {
    setTimeframe(newTimeframe)
    setChartConfig({ ...chartConfig, timeframe: newTimeframe })
  }

  const handleReplayToggle = () => {
    setReplayState({ ...replayState, enabled: !replayState.enabled })
  }

  const handleSaveLayout = () => {
    const layoutName = prompt('Enter layout name:', currentLayout.name)
    if (layoutName) {
      const savedLayout = {
        ...currentLayout,
        id: `layout_${Date.now()}`,
        name: layoutName,
        savedAt: Date.now(),
      }
      setSavedLayouts([...savedLayouts, savedLayout])
      alert(`Layout "${layoutName}" saved!`)
    }
  }

  const handleLoadLayout = () => {
    if (savedLayouts.length === 0) {
      alert('No saved layouts')
      return
    }

    // Simple layout selector (could be a modal in production)
    const layoutNames = savedLayouts.map((l, i) => `${i + 1}. ${l.name}`).join('\n')
    const selection = prompt(`Select layout:\n${layoutNames}\n\nEnter number:`)
    if (selection) {
      const index = parseInt(selection) - 1
      if (index >= 0 && index < savedLayouts.length) {
        setCurrentLayout(savedLayouts[index])
        alert(`Loaded layout: ${savedLayouts[index].name}`)
      }
    }
  }

  const handleLogout = () => {
    if (confirm('Are you sure you want to logout?')) {
      console.log('Logout')
      // Would navigate to login page
    }
  }

  return (
    <div className="h-screen flex flex-col bg-gray-950 text-white">
      {/* Global Header */}
      <GlobalHeader
        user={MOCK_USER}
        accounts={MOCK_ACCOUNTS}
        selectedAccountId={selectedAccountId}
        onAccountSelect={setSelectedAccountId}
        activeUniverse={activeUniverse}
        universes={MOCK_UNIVERSES}
        onUniverseChange={handleUniverseChange}
        onAddUniverse={handleAddUniverse}
        theme={theme}
        onThemeChange={setTheme}
        onLogout={handleLogout}
      />

      {/* Control Panel */}
      <ControlPanel
        filters={filters}
        onFiltersChange={handleFiltersChange}
        timeframe={timeframe}
        onTimeframeChange={handleTimeframeChange}
        replayState={replayState}
        onReplayToggle={handleReplayToggle}
        onSaveLayout={handleSaveLayout}
        onLoadLayout={handleLoadLayout}
        savedLayouts={savedLayouts}
      />

      {/* Universe Page (Main Content) */}
      <UniversePage
        layout={currentLayout}
        filters={filters}
        chartConfig={chartConfig}
        onChartConfigChange={(updates) => setChartConfig({ ...chartConfig, ...updates })}
        replayTime={replayState.enabled ? replayState.currentTime : undefined}
      />
    </div>
  )
}

export default MonitorV2
