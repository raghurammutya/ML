import React, { useMemo, useRef, useState, useLayoutEffect, useCallback, useEffect } from 'react'
import styles from './TradingDashboard.module.css'
import { TopControlPanel } from '../components/TopControlPanel'
import { ResizableSplit } from '../components/layout/ResizableSplit'
import {
  Timeframe,
  TradingDashboardState,
  SymbolFilterState,
} from '../components/tradingDashboard/types'
import { MonitorSyncProvider, useMonitorSync } from '../components/nifty-monitor/MonitorSyncContext'
import UnderlyingChart, {
  type UnderlyingChartProps,
  type UnderlyingContextAction,
} from '../components/nifty-monitor/UnderlyingChart'
import SideTabsPanel from '../components/tradingDashboard/SideTabsPanel'
import TradingAccountsPanel from '../components/tradingDashboard/TradingAccountsPanel'
import StrategySelector from '../components/tradingDashboard/StrategySelector'
import StrategyPnlPanel from '../components/tradingDashboard/StrategyPnlPanel'
import StrategyInstrumentsPanel from '../components/tradingDashboard/StrategyInstrumentsPanel'
import StrategyM2MChart from '../components/tradingDashboard/StrategyM2MChart'
import StrategyDrawer from '../components/tradingDashboard/StrategyDrawer'
import { useSymbolUniverse } from '../hooks/useSymbolUniverse'
import { useIndicatorCatalog } from '../hooks/useIndicatorCatalog'
import { searchTradableSymbols } from '../services/instruments'
import { fetchMonitorMetadata } from '../services/monitor'
import { displayUnderlyingSymbol, normalizeUnderlyingSymbol } from '../utils/symbols'
import type { MonitorOptionStrike } from '../types'
import MiniChartsPanel from '../components/tradingDashboard/MiniChartsPanel'
import OptionsRadar from '../components/tradingDashboard/OptionsRadar'
import OptionChart from '../components/tradingDashboard/OptionChart'
import { buildOiProfile } from '../components/tradingDashboard/oiProfile'
import OiProfileRail from '../components/tradingDashboard/OiProfileRail'
import OiChangePanel from '../components/tradingDashboard/OiChangePanel'
import {
  MOCK_TRADING_ACCOUNTS,
  TradingAccount,
  StrategySnapshot,
} from '../components/tradingDashboard/tradingAccounts'
import { useFoAnalytics } from '../hooks/useFoAnalytics'
import type { FoAnalyticsState } from '../hooks/useFoAnalytics'

const INITIAL_PRIMARY_WIDTH = 960
const SECONDARY_CHART_WIDTH = 420
const BASE_SIDE_TABS_WIDTH = 220
const SIDE_TABS_WIDTH_MIN = 180
const SIDE_TABS_WIDTH_MAX = 580
const GRID_GAP = 12
const CHART_HEIGHT = 420
const MONEYNESS_BUCKETS = [
  'ATM',
  ...Array.from({ length: 10 }, (_, index) => `OTM${index + 1}`),
  ...Array.from({ length: 10 }, (_, index) => `ITM${index + 1}`),
]

const FALLBACK_EXPIRIES = ['2025-11-07', '2025-11-14', '2025-11-28']

type RightPanePageType = 'futures' | 'call-strike' | 'put-strike' | 'straddle-strike'

interface RightPanePage {
  id: string
  title: string
  type: RightPanePageType
  symbol: string
  expiry?: string | null
  price?: number | null
  strike?: number | null
  optionSide?: 'call' | 'put' | 'straddle'
  pinned?: boolean
  createdAt: number
}

const formatExpiryLabel = (iso?: string | null): string => {
  if (!iso) return 'Nearest Expiry'
  const parsed = new Date(`${iso}T00:00:00Z`)
  if (Number.isNaN(parsed.getTime())) {
    return iso
  }
  return parsed.toLocaleDateString('en-IN', {
    month: 'short',
    day: 'numeric',
  })
}

const buildRightPaneId = (
  type: RightPanePageType,
  symbol: string,
  timeframe: UnderlyingChartProps['timeframe'],
  suffix?: string | number,
): string => {
  const base = `right-${type}-${symbol}-${timeframe}`
  return suffix != null ? `${base}-${suffix}` : base
}

const TradingDashboard: React.FC = () => {
  const [dashboardState, setDashboardState] = useState<TradingDashboardState>({
    tabs: ['NIFTY', 'BANKNIFTY', 'FINNIFTY'],
    activeTab: 'NIFTY',
    replayEnabled: false,
    replaySpeed: 1,
    timeframe: '5min',
    selectedIndicators: [],
    alertCount: 3,
    messageCount: 1,
  })

  const { tabs, activeTab, replayEnabled, replaySpeed, timeframe, selectedIndicators, alertCount, messageCount } =
    dashboardState

  const tradingAccounts = useMemo<TradingAccount[]>(() => MOCK_TRADING_ACCOUNTS, [])
  const [openAccountId, setOpenAccountId] = useState<string | null>(null)
  const [openStrategyId, setOpenStrategyId] = useState<string | null>(null)
  const [rightPages, setRightPages] = useState<RightPanePage[]>([])
  const [activeRightPageId, setActiveRightPageId] = useState<string | null>(null)

  const monitorTimeframe = useMemo<UnderlyingChartProps['timeframe']>(() => {
    switch (timeframe) {
      case '1min':
        return '1'
      case '2min':
        return '2'
      case '3min':
        return '3'
      case '5min':
        return '5'
      case '15min':
        return '15'
      case '30min':
        return '30'
      case '1hr':
        return '60'
      case '1day':
      default:
        return '1D'
    }
  }, [timeframe])

  const analytics = useFoAnalytics(activeTab, monitorTimeframe)
  const expiryValues = useMemo(() => analytics.expiryDetails.map((detail) => detail.date), [analytics.expiryDetails])
  const expiryOptions = useMemo(
    () =>
      analytics.expiryDetails.map((detail) => ({
        value: detail.date,
        label: detail.relative_label_today
          ? `${detail.relative_label_today} • ${formatExpiryLabel(detail.date)}`
          : formatExpiryLabel(detail.date),
      })),
    [analytics.expiryDetails],
  )
  const moneynessOptions = useMemo(
    () =>
      MONEYNESS_BUCKETS.map((bucket) => ({
        value: bucket,
        label:
          bucket === 'ATM'
            ? 'ATM'
            : bucket.startsWith('OTM')
              ? `OTM +${bucket.slice(3)}`
              : `ITM +${bucket.slice(3)}`,
      })),
    [],
  )
  const [symbolFilters, setSymbolFilters] = useState<Record<string, SymbolFilterState>>({})

  const arraysEqual = useCallback((a: string[], b: string[]) => {
    if (a.length !== b.length) return false
    for (let index = 0; index < a.length; index += 1) {
      if (a[index] !== b[index]) return false
    }
    return true
  }, [])

  const createDefaultFilterState = useCallback(
    (_symbol: string, previous?: SymbolFilterState): SymbolFilterState => {
      const baseExpiries = expiryValues.length ? [...expiryValues] : previous?.selectedExpiries ?? []
      const fallbackExpiries = baseExpiries.length ? baseExpiries : FALLBACK_EXPIRIES
      const sanitizedExpiries = (previous?.selectedExpiries ?? fallbackExpiries).filter((value) =>
        fallbackExpiries.includes(value),
      )
      const selectedExpiries = sanitizedExpiries.length ? sanitizedExpiries : fallbackExpiries
      const fallbackMoneyness = ['ATM']
      const sanitizedMoneyness = (previous?.selectedMoneyness ?? fallbackMoneyness).filter((value) =>
        MONEYNESS_BUCKETS.includes(value),
      )
      const selectedMoneyness = sanitizedMoneyness.length ? sanitizedMoneyness : fallbackMoneyness
      const rightExpiry =
        previous?.rightExpiry && fallbackExpiries.includes(previous.rightExpiry)
          ? previous.rightExpiry
          : fallbackExpiries[0] ?? null
      return {
        selectedExpiries,
        selectedMoneyness,
        rightExpiry,
      }
    },
    [expiryValues],
  )

  useEffect(() => {
    if (!expiryValues.length) return
    setSymbolFilters((prev) => {
      const existing = prev[activeTab]
      const defaults = createDefaultFilterState(activeTab, existing)
      if (
        existing &&
        arraysEqual(existing.selectedExpiries, defaults.selectedExpiries) &&
        arraysEqual(existing.selectedMoneyness, defaults.selectedMoneyness) &&
        existing.rightExpiry === defaults.rightExpiry
      ) {
        return prev
      }
      return {
        ...prev,
        [activeTab]: defaults,
      }
    })
  }, [activeTab, arraysEqual, createDefaultFilterState, expiryValues])

  const currentFilters = symbolFilters[activeTab]

  useEffect(() => {
    if (!currentFilters?.rightExpiry) return
    setRightPages((prev) => prev.map((page) => ({ ...page, expiry: currentFilters.rightExpiry })))
  }, [currentFilters?.rightExpiry])

  const handleExpiriesFilterChange = useCallback(
    (values: string[]) => {
      const valid = values.filter((value) => expiryValues.includes(value))
      const nextValues = valid.length ? valid : [...expiryValues]
      setSymbolFilters((prev) => {
        const base = createDefaultFilterState(activeTab, prev[activeTab])
        return {
          ...prev,
          [activeTab]: {
            ...base,
            selectedExpiries: nextValues,
          },
        }
      })
    },
    [activeTab, createDefaultFilterState, expiryValues],
  )

  const handleMoneynessFilterChange = useCallback(
    (values: string[]) => {
      const valid = values.filter((value) => MONEYNESS_BUCKETS.includes(value))
      const nextValues = valid.length ? valid : ['ATM']
      setSymbolFilters((prev) => {
        const base = createDefaultFilterState(activeTab, prev[activeTab])
        return {
          ...prev,
          [activeTab]: {
            ...base,
            selectedMoneyness: nextValues,
          },
        }
      })
    },
    [activeTab, createDefaultFilterState],
  )

  const handleRightExpiryChange = useCallback(
    (value: string) => {
      setSymbolFilters((prev) => {
        const base = createDefaultFilterState(activeTab, prev[activeTab])
        const nextExpiry = value && expiryValues.includes(value) ? value : base.rightExpiry
        return {
          ...prev,
          [activeTab]: {
            ...base,
            rightExpiry: nextExpiry,
          },
        }
      })
    },
    [activeTab, createDefaultFilterState, expiryValues],
  )

  const selectedExpiries = currentFilters?.selectedExpiries ?? expiryValues
  const selectedMoneyness = currentFilters?.selectedMoneyness ?? MONEYNESS_BUCKETS
  const rightExpiry = currentFilters?.rightExpiry ?? (expiryValues[0] ?? null)

  const selectExpiry = useCallback(
    (candidate?: string | null): string | null => {
      const parse = (iso?: string | null): Date | null => {
        if (!iso) return null
        const date = new Date(`${iso}T00:00:00Z`)
        return Number.isNaN(date.getTime()) ? null : date
      }

      const today = new Date()
      today.setUTCHours(0, 0, 0, 0)

      if (candidate && analytics.expiries.includes(candidate)) {
        const candidateDate = parse(candidate)
        if (candidateDate && candidateDate >= today) {
          return candidate
        }
      }

      const upcoming = analytics.expiries
        .map((iso) => ({ iso, date: parse(iso) }))
        .filter((entry): entry is { iso: string; date: Date } => Boolean(entry.date))
        .filter((entry) => entry.date >= today)
        .sort((a, b) => a.date.getTime() - b.date.getTime())

      if (upcoming.length) {
        return upcoming[0].iso
      }

      if (candidate && analytics.expiries.includes(candidate) && parse(candidate)) {
        return candidate
      }

      return analytics.expiries.find((iso) => parse(iso)) ?? null
    },
    [analytics.expiries],
  )

  const nearestExpiry = useMemo(() => selectExpiry(), [selectExpiry])

  const createFuturesPage = useCallback(
    (expiry?: string | null): RightPanePage => ({
      id: buildRightPaneId('futures', activeTab, monitorTimeframe),
      title: expiry ? `Futures ${formatExpiryLabel(expiry)}` : 'Futures',
      type: 'futures',
      symbol: activeTab,
      expiry: expiry ?? null,
      price: null,
      pinned: true,
      createdAt: 0,
    }),
    [activeTab, monitorTimeframe],
  )

  useEffect(() => {
    const basePage = createFuturesPage(nearestExpiry)
    setRightPages((prev) => {
      const existingIndex = prev.findIndex((page) => page.id === basePage.id)
      if (existingIndex === -1) {
        return [basePage, ...prev]
      }
      const existing = prev[existingIndex]
      if (
        existing.expiry !== basePage.expiry ||
        existing.symbol !== basePage.symbol ||
        existing.title !== basePage.title
      ) {
        const next = [...prev]
        next[existingIndex] = {
          ...existing,
          title: basePage.title,
          expiry: basePage.expiry,
          symbol: basePage.symbol,
          pinned: existing.pinned,
        }
        return next
      }
      return prev
    })
    setActiveRightPageId((current) => {
      if (!current || current === basePage.id) {
        return basePage.id
      }
      return current
    })
  }, [createFuturesPage, nearestExpiry])

  const findNearestStrike = useCallback(
    (expiry: string | null, price: number | null): number | null => {
      if (!expiry) return null
      const targetLine = analytics.strike.delta.find((line) => line.expiry === expiry)
      if (!targetLine) return null
      const strikeSet = new Set<number>()
      targetLine.calls.forEach((point) => strikeSet.add(point.strike))
      targetLine.puts.forEach((point) => strikeSet.add(point.strike))
      if (strikeSet.size === 0) return null
      const strikes = Array.from(strikeSet).sort((a, b) => a - b)
      if (price == null) {
        return strikes[Math.floor(strikes.length / 2)]
      }
      let closest = strikes[0]
      let bestDiff = Math.abs(strikes[0] - price)
      for (let index = 1; index < strikes.length; index += 1) {
        const strike = strikes[index]
        const diff = Math.abs(strike - price)
        if (diff < bestDiff) {
          closest = strike
          bestDiff = diff
        }
      }
    return closest
  },
  [analytics.strike.delta],
)

  const isValidExpiry = useCallback(
    (expiry: string | null | undefined): expiry is string =>
      !!expiry && analytics.expiries.includes(expiry),
    [analytics.expiries],
  )

const buildStrikePageTitle = useCallback((symbol: string) => displayUnderlyingSymbol(symbol), [])

  const appendRightPage = useCallback((page: RightPanePage) => {
    setRightPages((prev) => [...prev, page])
    setActiveRightPageId(page.id)
  }, [])

  const handleUnderlyingContextAction = useCallback(
    (action: UnderlyingContextAction) => {
      if (action.kind !== 'show-chart') {
        return
      }
      const variant: RightPanePageType = action.variant
      const normalizedSymbol = normalizeUnderlyingSymbol(action.symbol)
      const defaultStrikeGap = normalizedSymbol.includes('BANK') ? 100 : 50
      const clickPrice =
        typeof action.price === 'number' && Number.isFinite(action.price)
          ? Number(action.price)
          : null

      const computeGapAlignedStrike = (price: number | null, gap: number): number | null => {
        if (price == null || !Number.isFinite(price) || gap <= 0) return null
        return Math.round(price / gap) * gap
      }

      const perform = async () => {
        const fallbackExpiry = selectExpiry()
        const orderedExpiries = [
          ...(fallbackExpiry ? [fallbackExpiry] : []),
          ...analytics.expiries.filter((entry) => entry !== fallbackExpiry),
        ].filter(isValidExpiry)

        const selectStrikeForExpiry = (
          expiry: string,
          strikeGap: number,
          referencePrice: number | null,
        ): number | null => {
          const aligned = computeGapAlignedStrike(referencePrice, strikeGap)
          if (aligned != null) return aligned
          return findNearestStrike(expiry, referencePrice)
        }

        let resolvedExpiry: string | null = orderedExpiries[0] ?? null
        let selectedStrike: number | null = null
        if (resolvedExpiry) {
          selectedStrike =
            computeGapAlignedStrike(clickPrice, defaultStrikeGap) ??
            findNearestStrike(resolvedExpiry, action.price ?? null)
        }

        try {
          const metadata = await fetchMonitorMetadata({ symbol: normalizedSymbol, otm_levels: 50 })
          const strikeGapCandidate =
            metadata.meta?.strike_gap != null ? Number(metadata.meta.strike_gap) : null
          const strikeGap =
            strikeGapCandidate && Number.isFinite(strikeGapCandidate) && strikeGapCandidate > 0
              ? strikeGapCandidate
              : defaultStrikeGap

          const metadataOptions = metadata.options ?? []
          let bestMatch: { expiry: string; strike: number } | null = null

          for (const candidateExpiry of orderedExpiries) {
            const entry = metadataOptions.find((option) => option.expiry === candidateExpiry)
            if (!entry || !entry.strikes?.length) continue

            const referencePrice =
              typeof action.price === 'number' &&
              Number.isFinite(action.price) &&
              candidateExpiry === fallbackExpiry
                ? Number(action.price)
                : metadata.underlying?.last_price ??
                  entry.atm_strike ??
                  clickPrice ??
                  null

            const alignedStrike = selectStrikeForExpiry(candidateExpiry, strikeGap, referencePrice)
            const nearestStrike = entry.strikes.reduce<MonitorOptionStrike | null>((closest, current) => {
              if (!closest) return current
              if (alignedStrike == null) return closest
              const currentDiff = Math.abs(current.strike - alignedStrike)
              const closestDiff = Math.abs(closest.strike - alignedStrike)
              return currentDiff < closestDiff ? current : closest
            }, entry.strikes[0] ?? null)

            if (!nearestStrike) continue

            const requiresCall = variant === 'call-strike' || variant === 'straddle-strike'
            const requiresPut = variant === 'put-strike' || variant === 'straddle-strike'
            const hasCall = !requiresCall || !!nearestStrike.call?.instrument_token
            const hasPut = !requiresPut || !!nearestStrike.put?.instrument_token

            if (!hasCall || !hasPut) continue

            bestMatch = { expiry: candidateExpiry, strike: nearestStrike.strike }
            break
          }

          if (bestMatch) {
            resolvedExpiry = bestMatch.expiry
            selectedStrike = bestMatch.strike
          } else {
            console.warn('[TradingDashboard] No strike with populated option legs found; using fallback expiry')
            resolvedExpiry = orderedExpiries.find(isValidExpiry) ?? analytics.expiries[0] ?? null
            if (resolvedExpiry) {
              selectedStrike =
                computeGapAlignedStrike(clickPrice, strikeGap) ??
                findNearestStrike(resolvedExpiry, action.price ?? null)
            } else {
              selectedStrike = null
            }
          }
        } catch (error) {
          console.error('[TradingDashboard] Failed to hydrate strike metadata', error)
        }

        if (!isValidExpiry(resolvedExpiry)) {
          resolvedExpiry = analytics.expiries[0] ?? null
        }

        if (selectedStrike == null) {
          selectedStrike = computeGapAlignedStrike(clickPrice, defaultStrikeGap)
        }

        const page: RightPanePage = {
          id: buildRightPaneId(variant, action.symbol, monitorTimeframe, Date.now()),
          title: buildStrikePageTitle(action.symbol),
          type: variant,
          symbol: action.symbol,
          expiry: resolvedExpiry,
          price: action.price ?? null,
          strike: selectedStrike ?? null,
          optionSide: variant === 'put-strike' ? 'put' : variant === 'call-strike' ? 'call' : 'straddle',
          pinned: false,
          createdAt: Date.now(),
        }
        appendRightPage(page)
      }

      void perform()
    },
    [
      selectExpiry,
      findNearestStrike,
      monitorTimeframe,
      buildStrikePageTitle,
      appendRightPage,
    ],
  )

  const handleSelectRightPage = useCallback((pageId: string) => {
    setActiveRightPageId(pageId)
  }, [])

  const handleTogglePinRightPage = useCallback((pageId: string) => {
    setRightPages((prev) =>
      prev.map((page) => (page.id === pageId ? { ...page, pinned: !page.pinned } : page)),
    )
  }, [])

  const handleCloseRightPage = useCallback(
    (pageId: string) => {
      let nextActiveId: string | null = null
      setRightPages((prev) => {
        const target = prev.find((page) => page.id === pageId)
        if (!target || target.pinned) {
          return prev
        }
        const filtered = prev.filter((page) => page.id !== pageId)
        if (!filtered.length) {
          const fallback = createFuturesPage(nearestExpiry)
          nextActiveId = fallback.id
          return [fallback]
        }
        if (activeRightPageId === pageId) {
          nextActiveId = filtered[0].id
        } else {
          nextActiveId = activeRightPageId
        }
        return filtered
      })
      if (nextActiveId) {
        setActiveRightPageId(nextActiveId)
      }
    },
    [activeRightPageId, createFuturesPage, nearestExpiry],
  )

  const { symbols: universeSymbols } = useSymbolUniverse()
  const { options: indicatorOptions } = useIndicatorCatalog()
  const handleSearchSymbols = useCallback((query: string) => searchTradableSymbols(query, 60), [])

  const updateState = (partial: Partial<TradingDashboardState>) => {
    setDashboardState((prev) => ({ ...prev, ...partial }))
  }

  const handleTabClick = (symbol: string) => {
    updateState({ activeTab: symbol })
    console.log('Switched to universe:', symbol)
  }

  const handleCloseTab = (symbol: string) => {
    setDashboardState((prev) => {
      if (prev.tabs.length === 1) {
        console.warn('Cannot close the last tab')
        return prev
      }

      const nextTabs = prev.tabs.filter((tab) => tab !== symbol)
      const nextActive = prev.activeTab === symbol ? nextTabs[0] ?? '' : prev.activeTab
      console.log('Closed tab:', symbol)
      return {
        ...prev,
        tabs: nextTabs,
        activeTab: nextActive,
      }
    })
  }

  const handleAddTabs = (symbols: string[]) => {
    setDashboardState((prev) => {
      const newSymbols = symbols.filter((symbol) => !prev.tabs.includes(symbol))
      if (newSymbols.length === 0) {
        return prev
      }
      console.log('Added tabs:', newSymbols)
      return {
        ...prev,
        tabs: [...prev.tabs, ...newSymbols],
        activeTab: newSymbols[0],
      }
    })
  }

  const handleReplayToggle = (enabled: boolean) => {
    updateState({ replayEnabled: enabled })
    console.log('Replay mode:', enabled ? 'enabled' : 'disabled')
  }

  const handleReplaySpeedChange = (speed: number) => {
    updateState({ replaySpeed: speed })
    console.log('Replay speed:', `${speed}x`)
  }

  const handleTimeframeChange = (newTimeframe: Timeframe) => {
    updateState({ timeframe: newTimeframe })
    console.log('Timeframe changed to:', newTimeframe)
  }

  const handleIndicatorsChange = (indicators: string[]) => {
    updateState({ selectedIndicators: indicators })
    console.log('Indicators selected:', indicators)
  }

  const handleSaveLayout = () => {
    console.log('Save layout clicked')
  }

  const handleLoadLayout = () => {
    console.log('Load layout clicked')
  }

  const handleAlertsClick = () => {
    console.log('Alerts clicked - count:', alertCount)
  }

  const handleMessagesClick = () => {
    console.log('Messages clicked - count:', messageCount)
  }

  // Account selection now handled by TradingAccountContext
  // const handleAccountSelect = (accountId: string) => {
  //   setOpenAccountId(accountId)
  //   const account = tradingAccounts.find((item) => item.id === accountId)
  //   setOpenStrategyId(account?.strategies[0]?.id ?? null)
  // }

  const handleCloseDrawer = () => {
    setOpenAccountId(null)
    setOpenStrategyId(null)
  }

  const handleStrategySelect = (strategyId: string) => {
    setOpenStrategyId(strategyId)
  }

  const activeAccount = openAccountId
    ? tradingAccounts.find((account) => account.id === openAccountId) ?? null
    : null

  const activeStrategy: StrategySnapshot | null =
    activeAccount?.strategies.find((strategy) => strategy.id === openStrategyId) ?? null

  return (
    <div className={styles.page}>
      <TopControlPanel
        tabs={tabs}
        activeTab={activeTab}
        onTabClick={handleTabClick}
        onCloseTab={handleCloseTab}
        onAddTabs={handleAddTabs}
        replayEnabled={replayEnabled}
        onReplayToggle={handleReplayToggle}
        replaySpeed={replaySpeed}
        onReplaySpeedChange={handleReplaySpeedChange}
        timeframe={timeframe}
        onTimeframeChange={handleTimeframeChange}
        selectedIndicators={selectedIndicators}
        onIndicatorsChange={handleIndicatorsChange}
        alertCount={alertCount}
        messageCount={messageCount}
        onSaveLayout={handleSaveLayout}
        onLoadLayout={handleLoadLayout}
        onAlertsClick={handleAlertsClick}
        onMessagesClick={handleMessagesClick}
        availableSymbols={universeSymbols}
        onSearchSymbols={handleSearchSymbols}
        indicatorOptions={indicatorOptions}
        expiryOptions={expiryOptions}
        selectedExpiries={selectedExpiries}
        onExpiriesChange={handleExpiriesFilterChange}
        moneynessOptions={moneynessOptions}
        selectedMoneyness={selectedMoneyness}
        onMoneynessChange={handleMoneynessFilterChange}
      />

      <MonitorSyncProvider>
        <ResizableSplit
          className={styles.split}
          initialPrimaryPercentage={62}
          minPrimaryPx={520}
          minSecondaryPx={320}
          primary={
            <PrimaryColumn
              activeTab={activeTab}
              monitorTimeframe={monitorTimeframe}
              analytics={analytics}
              selectedExpiries={selectedExpiries}
              selectedMoneyness={selectedMoneyness}
              onContextAction={handleUnderlyingContextAction}
            />
          }
          secondary={
            <SecondaryColumn
              activeTab={activeTab}
              monitorTimeframe={monitorTimeframe}
              pages={rightPages}
              activePageId={activeRightPageId}
              onSelectPage={handleSelectRightPage}
              onClosePage={handleCloseRightPage}
              onTogglePin={handleTogglePinRightPage}
              analytics={analytics}
              onContextAction={handleUnderlyingContextAction}
              resolveExpiry={selectExpiry}
              expiryOptions={expiryOptions}
              rightExpiry={rightExpiry}
              onRightExpiryChange={handleRightExpiryChange}
            />
          }
        />
      </MonitorSyncProvider>
      {activeAccount && activeStrategy && (
        <StrategyDrawer
          account={activeAccount}
          strategy={activeStrategy}
          onSelectStrategy={handleStrategySelect}
          onClose={handleCloseDrawer}
        />
      )}
    </div>
  )
}

// Wrap with Auth, TradingAccount, and Strategy providers
import { AuthProvider } from '../contexts/AuthContext'
import { TradingAccountProvider } from '../contexts/TradingAccountContext'
import { StrategyProvider } from '../contexts/StrategyContext'

const TradingDashboardWithProviders = () => {
  return (
    <AuthProvider>
      <TradingAccountProvider>
        <StrategyProvider>
          <TradingDashboard />
        </StrategyProvider>
      </TradingAccountProvider>
    </AuthProvider>
  )
}

export default TradingDashboardWithProviders

interface PrimaryColumnProps {
  activeTab: string
  monitorTimeframe: UnderlyingChartProps['timeframe']
  analytics: FoAnalyticsState
  selectedExpiries: string[]
  selectedMoneyness: string[]
  onContextAction?: (action: UnderlyingContextAction) => void
}

const PrimaryColumn: React.FC<PrimaryColumnProps> = ({
  activeTab,
  monitorTimeframe,
  analytics,
  selectedExpiries,
  selectedMoneyness,
  onContextAction,
}) => {
  const { crosshairRatio } = useMonitorSync()
  const [primaryWidth, setPrimaryWidth] = useState<number>(INITIAL_PRIMARY_WIDTH)
  const initialSideWidth = BASE_SIDE_TABS_WIDTH
  const [sideWidth, setSideWidth] = useState<number>(initialSideWidth)
  const stackRef = useRef<HTMLDivElement | null>(null)
  const [surfaceMetrics, setSurfaceMetrics] = useState<{ left: number; width: number; height: number }>(() => ({
    left: initialSideWidth + GRID_GAP + 12,
    width: Math.max(INITIAL_PRIMARY_WIDTH - 24, 600),
    height: CHART_HEIGHT,
  }))
  const chartHeight = surfaceMetrics.height || CHART_HEIGHT
  const totalWidth = primaryWidth + 2 * (sideWidth + GRID_GAP)
  const stackStyle = {
    '--chart-width': `${primaryWidth}px`,
    '--tabs-width': `${sideWidth}px`,
    width: `${Math.round(totalWidth)}px`,
  } as React.CSSProperties

  const effectiveWidth = surfaceMetrics.width > 0 ? surfaceMetrics.width : Math.max(primaryWidth - 24, 0)
  const defaultOffset = sideWidth + GRID_GAP + 12
  const effectiveOffset = surfaceMetrics.left > 0 ? surfaceMetrics.left : defaultOffset

  useLayoutEffect(() => {
    if (!stackRef.current) return
    const stackEl = stackRef.current

    const resolveSurface = () =>
      (stackEl.querySelector('[data-surface-id="primary-underlying"]') as HTMLElement | null) ?? null

    const updateMetrics = () => {
      const surface = resolveSurface()
      if (!surface) return
      const stackRect = stackEl.getBoundingClientRect()
      const surfaceRect = surface.getBoundingClientRect()
      setSurfaceMetrics({
        left: surfaceRect.left - stackRect.left,
        width: surfaceRect.width,
        height: surfaceRect.height || CHART_HEIGHT,
      })
    }

    updateMetrics()
    window.addEventListener('resize', updateMetrics)

    let resizeObserver: ResizeObserver | null = null
    const surface = resolveSurface()
    if (surface && typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(() => updateMetrics())
      resizeObserver.observe(surface)
    }

    return () => {
      window.removeEventListener('resize', updateMetrics)
      resizeObserver?.disconnect()
    }
  }, [primaryWidth, sideWidth, activeTab, monitorTimeframe])

  const crosshairLeft =
    crosshairRatio != null && effectiveWidth
      ? effectiveOffset + crosshairRatio * effectiveWidth
      : null

  const radarValues = useMemo(() => {
    const record: Record<string, number | null> = {}
    analytics.radar.forEach((snapshot) => {
      record[snapshot.metric] =
        typeof snapshot.value === 'number' && Number.isFinite(snapshot.value)
          ? snapshot.value
          : null
    })
    return record
  }, [analytics.radar])

  const oiProfile = useMemo(
    () => buildOiProfile(analytics.strike.oi, selectedExpiries, selectedMoneyness),
    [analytics.strike.oi, selectedExpiries, selectedMoneyness],
  )

  return (
    <main className={styles.main}>
      <div className={styles.chartStack} ref={stackRef} style={stackStyle}>
        {crosshairLeft != null && (
          <div className={styles.crosshairGuide} style={{ left: `${crosshairLeft}px` }} />
        )}

        <div className={styles.resizeRow}>
          <label htmlFor="primary-width">Width</label>
          <input
            id="primary-width"
            type="range"
            min={780}
            max={1340}
            step={20}
            value={primaryWidth}
            onChange={(event) => setPrimaryWidth(Number(event.target.value))}
          />
          <span>{primaryWidth}px</span>
        </div>
        <div className={styles.resizeRow}>
          <label htmlFor="side-width">Side panels</label>
          <input
            id="side-width"
            type="range"
            min={SIDE_TABS_WIDTH_MIN}
            max={SIDE_TABS_WIDTH_MAX}
            step={20}
            value={sideWidth}
            onChange={(event) => setSideWidth(Number(event.target.value))}
          />
          <span>{Math.round(sideWidth)}px</span>
        </div>

        <div className={styles.chartShell}>
          <div className={styles.sideTabsColumn}>
            <div className={styles.sideTabsStack}>
              <SideTabsPanel
                symbol={activeTab}
                timeframe={monitorTimeframe}
                title="Call"
                side="left"
                analytics={analytics}
                chartHeight={chartHeight}
                visibleExpiries={selectedExpiries}
                visibleMoneyness={selectedMoneyness}
              />
            </div>
          </div>
          <div className={styles.centerChartFrame} style={{ width: primaryWidth }}>
            <div className={styles.centerChartInner}>
              <UnderlyingChart
                key={`${activeTab}-${monitorTimeframe}-center`}
                symbol={activeTab}
                timeframe={monitorTimeframe}
                surfaceId="primary-underlying"
                reportDimensions
                enableRealtime
                onContextAction={onContextAction}
              />
              {oiProfile.perStrike.length > 0 && (
                <div className={styles.oiRail}>
                  <OiProfileRail data={oiProfile.perStrike} />
                </div>
              )}
            </div>
          </div>
          <div className={styles.sideTabsColumn}>
            <SideTabsPanel
              symbol={activeTab}
              timeframe={monitorTimeframe}
              title="Put"
              side="right"
              analytics={analytics}
              chartHeight={chartHeight}
              visibleExpiries={selectedExpiries}
              visibleMoneyness={selectedMoneyness}
            />
          </div>
        </div>

        <div className={styles.analyticsRow}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <MiniChartsPanel
              symbol={activeTab}
              timeframe={monitorTimeframe}
              chartWidth={effectiveWidth}
              offsetLeft={effectiveOffset}
              panels={analytics.moneyness}
              loading={analytics.loading}
              visibleExpiries={selectedExpiries}
              visibleMoneyness={selectedMoneyness}
            />
            {oiProfile.perExpiry.length > 0 && <OiChangePanel entries={oiProfile.perExpiry} />}
          </div>
          <OptionsRadar
            symbol={activeTab}
            timeframe={monitorTimeframe}
            width={Math.max(Math.min(Math.round(effectiveWidth * 0.24), 360), 200)}
            values={radarValues}
          />
          <div className={styles.accountsPanel}>
            <StrategySelector />
            <TradingAccountsPanel />
            <StrategyPnlPanel />
            <StrategyInstrumentsPanel />
          </div>
        </div>
        <div className={styles.strategyChartRow}>
          <StrategyM2MChart />
        </div>
      </div>
    </main>
  )
}

interface SecondaryColumnProps {
  activeTab: string
  monitorTimeframe: UnderlyingChartProps['timeframe']
  pages: RightPanePage[]
  activePageId: string | null
  onSelectPage: (pageId: string) => void
  onClosePage: (pageId: string) => void
  onTogglePin: (pageId: string) => void
  analytics: FoAnalyticsState
  onContextAction?: (action: UnderlyingContextAction) => void
  resolveExpiry: (candidate?: string | null) => string | null
  expiryOptions: Array<{ value: string; label: string }>
  rightExpiry: string | null
  onRightExpiryChange?: (value: string) => void
}

const SecondaryColumn: React.FC<SecondaryColumnProps> = ({
  activeTab,
  monitorTimeframe,
  pages,
  activePageId,
  onSelectPage,
  onClosePage,
  onTogglePin,
  analytics,
  onContextAction,
  resolveExpiry,
  expiryOptions,
  rightExpiry,
  onRightExpiryChange,
}) => {
  const { crosshairRatio } = useMonitorSync()
  const [secondaryWidth, setSecondaryWidth] = useState<number>(SECONDARY_CHART_WIDTH)
  const stackRef = useRef<HTMLDivElement | null>(null)
  const [surfaceMetrics, setSurfaceMetrics] = useState<{ left: number; width: number }>({
    left: 0,
    width: SECONDARY_CHART_WIDTH,
  })
  const displayPages = useMemo(() => [...pages].sort((a, b) => a.createdAt - b.createdAt), [pages])
  const activePage = useMemo(() => {
    if (!displayPages.length) return null
    if (activePageId) {
      const found = displayPages.find((page) => page.id === activePageId)
      if (found) return found
    }
    return displayPages[0]
  }, [displayPages, activePageId])
  const effectiveRightExpiry = rightExpiry ?? (expiryOptions[0]?.value ?? null)

  useLayoutEffect(() => {
    if (!stackRef.current) return
    const stackEl = stackRef.current
    const resolveSurface = () =>
      (stackEl.querySelector('[data-surface-id="secondary-underlying"]') as HTMLElement | null) ?? null

    const updateMetrics = () => {
      const surface = resolveSurface()
      if (!surface) {
        setSurfaceMetrics({ left: 0, width: secondaryWidth })
        return
      }
      const stackRect = stackEl.getBoundingClientRect()
      const surfaceRect = surface.getBoundingClientRect()
      setSurfaceMetrics({
        left: surfaceRect.left - stackRect.left,
        width: surfaceRect.width,
      })
    }

    updateMetrics()
    window.addEventListener('resize', updateMetrics)

    let resizeObserver: ResizeObserver | null = null
    const surface = resolveSurface()
    if (surface && typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(() => updateMetrics())
      resizeObserver.observe(surface)
    }

    return () => {
      window.removeEventListener('resize', updateMetrics)
      resizeObserver?.disconnect()
    }
  }, [secondaryWidth, activeTab, monitorTimeframe, activePage])

  const effectiveWidth = surfaceMetrics.width || secondaryWidth
  const effectiveOffset = surfaceMetrics.left
  const crosshairLeft =
    crosshairRatio != null && effectiveWidth
      ? effectiveOffset + crosshairRatio * effectiveWidth
      : null

  const renderPageContent = () => {
    if (!activePage) {
      return (
        <div className={styles.sideCard}>
          <div className={styles.sideCardHeader}>
            <h2>No pages available</h2>
            <p>Right-click the underlying chart to open a view in this panel.</p>
          </div>
        </div>
      )
    }

    if (activePage.type === 'futures') {
      return (
        <>
          <div className={styles.sideChartFrame} style={{ width: secondaryWidth }}>
            <UnderlyingChart
              key={`${activePage.id}-${activeTab}-${monitorTimeframe}`}
              symbol={activeTab}
              timeframe={monitorTimeframe}
              surfaceId="secondary-underlying"
              reportDimensions
              enableRealtime
              onContextAction={onContextAction}
            />
          </div>

          <div className={styles.analyticsRow}>
          <MiniChartsPanel
            symbol={activeTab}
            timeframe={monitorTimeframe}
            chartWidth={effectiveWidth}
            offsetLeft={effectiveOffset}
            variant="compact"
            panels={analytics.moneyness}
            loading={analytics.loading}
            visibleExpiries={effectiveRightExpiry ? [effectiveRightExpiry] : undefined}
          />
            <OptionsRadar
              symbol={activeTab}
              timeframe={monitorTimeframe}
              width={Math.max(Math.round(effectiveWidth * 0.2), 120)}
            />
          </div>
        </>
      )
    }

    if (
      activePage.type === 'call-strike' ||
      activePage.type === 'put-strike' ||
      activePage.type === 'straddle-strike'
    ) {
      const fallbackExpiry = resolveExpiry(activePage.expiry ?? effectiveRightExpiry ?? null)
      const expiryLine =
        analytics.strike.delta.find((line) => line.expiry === fallbackExpiry) ?? analytics.strike.delta[0]
      const fallbackStrike =
        activePage.strike ??
        expiryLine?.calls[0]?.strike ??
        expiryLine?.puts[0]?.strike ??
        null

      if (!fallbackExpiry || fallbackStrike == null) {
        return (
          <div className={styles.sideCard}>
            <div className={styles.sideCardHeader}>
              <h2>{activePage.title}</h2>
              <p>Awaiting strike metadata to render option chart.</p>
            </div>
          </div>
        )
      }

      const chartSide =
        activePage.optionSide === 'call'
          ? 'call'
          : activePage.optionSide === 'put'
            ? 'put'
            : 'straddle'

      return (
        <>
          <OptionChart
            underlying={activeTab}
            expiry={fallbackExpiry}
            strike={fallbackStrike}
            timeframe={monitorTimeframe}
            side={chartSide}
            title={activePage.title}
          />

          <div className={styles.analyticsRow}>
          <MiniChartsPanel
            symbol={activeTab}
            timeframe={monitorTimeframe}
            chartWidth={effectiveWidth}
            offsetLeft={effectiveOffset}
            variant="compact"
            panels={analytics.moneyness}
            loading={analytics.loading}
            visibleExpiries={effectiveRightExpiry ? [effectiveRightExpiry] : undefined}
          />
            <OptionsRadar
              symbol={activeTab}
              timeframe={monitorTimeframe}
              width={Math.max(Math.round(effectiveWidth * 0.2), 120)}
            />
          </div>
        </>
      )
    }

    return (
      <div className={styles.sideCard}>
        <div className={styles.sideCardHeader}>
          <h2>{activePage.title}</h2>
          <p>
            This page is ready for strike analytics. Right-click the primary chart again to load a specific
            strike profile or pin this page for quick access.
          </p>
          {(activePage.expiry ?? effectiveRightExpiry ?? analytics.expiries[0]) && (
            <span className={styles.sideCardMeta}>
              Nearest expiry: {formatExpiryLabel(activePage.expiry ?? effectiveRightExpiry ?? analytics.expiries[0])}
            </span>
          )}
        </div>
      </div>
    )
  }

  const showResizeControl = Boolean(activePage)

  return (
    <aside className={styles.sidePanel}>
      <div className={styles.sideStack} ref={stackRef}>
        <div className={styles.pageTabs}>
          {displayPages.map((page) => {
            const isActive = page.id === activePage?.id
            return (
              <div
                key={page.id}
                className={`${styles.pageTab} ${isActive ? styles.pageTabActive : ''} ${
                  page.pinned ? styles.pageTabPinned : ''
                }`}
              >
                <button
                  type="button"
                  className={styles.pageTabButton}
                  onClick={() => onSelectPage(page.id)}
                >
                  {page.title}
                </button>
                <div className={styles.pageTabActions}>
                  <button
                    type="button"
                    className={`${styles.iconButton} ${page.pinned ? styles.iconButtonActive : ''}`}
                    onClick={() => onTogglePin(page.id)}
                    title={page.pinned ? 'Unpin page' : 'Pin page'}
                  >
                    📌
                  </button>
                  <button
                    type="button"
                    className={styles.iconButton}
                    onClick={() => onClosePage(page.id)}
                    disabled={page.pinned}
                    title={page.pinned ? 'Unpin to close' : 'Close page'}
                  >
                    ×
                  </button>
                </div>
              </div>
            )
          })}
        </div>

        {crosshairLeft != null && (
          <div className={styles.crosshairGuide} style={{ left: `${crosshairLeft}px` }} />
        )}

        {expiryOptions.length > 0 && (
          <div className={styles.sideFilterRow}>
            <label htmlFor="secondary-expiry">Expiry</label>
            <select
              id="secondary-expiry"
              value={effectiveRightExpiry ?? expiryOptions[0]?.value ?? ''}
              onChange={(event) => onRightExpiryChange?.(event.target.value)}
            >
              {expiryOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        )}

        {showResizeControl && (
          <div className={styles.resizeRow}>
            <label htmlFor="secondary-width">Width</label>
            <input
              id="secondary-width"
              type="range"
              min={360}
              max={960}
              step={20}
              value={secondaryWidth}
              onChange={(event) => setSecondaryWidth(Number(event.target.value))}
            />
            <span>{secondaryWidth}px</span>
          </div>
        )}

        {renderPageContent()}
      </div>
    </aside>
  )
}
