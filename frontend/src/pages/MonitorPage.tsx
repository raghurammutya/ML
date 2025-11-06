import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import UnderlyingChart from '../components/nifty-monitor/UnderlyingChart'
import PanelManager from '../components/nifty-monitor/PanelManager'
import HorizontalPanel from '../components/nifty-monitor/HorizontalPanel'
import VerticalPanel from '../components/nifty-monitor/VerticalPanel'
import { MonitorSyncProvider } from '../components/nifty-monitor/MonitorSyncContext'
import DerivativesChartPopup from '../components/ShowChartPopup/DerivativesChartPopup'
import ReplayControls from '../components/nifty-monitor/ReplayControls'
import ReplayWatermark from '../components/nifty-monitor/ReplayWatermark'
import { useReplayMode } from '../hooks/useReplayMode'
import { ResizableSplit } from '../components/layout/ResizableSplit'
import type {
  FoIndicatorDefinition,
  FoMoneynessSeries,
  FoRealtimeBucket,
  FoStrikeSeries,
  MonitorMetadataResponse,
  MonitorStreamMessage,
  MonitorSearchResult,
} from '../types'
import {
  fetchFoIndicators,
  fetchFoMoneynessSeries,
  fetchFoStrikeDistribution,
  connectFoStream,
} from '../services/fo'
import {
  fetchMonitorMetadata,
  createMonitorSession,
  deleteMonitorSession,
  fetchMonitorSnapshot,
  connectMonitorStream,
  searchMonitorSymbols,
} from '../services/monitor'
import { displayUnderlyingSymbol, normalizeUnderlyingSymbol } from '../utils/symbols'

type Timeframe = '1' | '2' | '3' | '5' | '15' | '30' | '60' | '1D'

interface PanelViewState {
  enabled: boolean
  collapsed: boolean
}

const TIMEFRAMES: Timeframe[] = ['1', '2', '3', '5', '15', '30', '60', '1D']
const COLORS = ['#26a69a', '#f97316', '#60a5fa', '#a855f7', '#f43f5e', '#facc15', '#38bdf8']
const REALTIME_FIELD_MAP: Record<string, keyof FoRealtimeBucket['strikes'][number]['call']> = {
  iv: 'iv',
  delta: 'delta',
  gamma: 'gamma',
  theta: 'theta',
  vega: 'vega',
  oi: 'oi',
}
const DEFAULT_STRIKE_GAP = Number(import.meta.env.VITE_FO_STRIKE_GAP ?? 50)
const DEFAULT_UNDERLYING = (import.meta.env.VITE_MONITOR_SYMBOL as string | undefined) ?? 'NIFTY50'
const aggregateRealtimeValue = (
  indicator: string,
  optionSide: string | undefined,
  strikeEntry: FoRealtimeBucket['strikes'][number]
): number | null => {
  const call = strikeEntry.call
  const put = strikeEntry.put
  const pick = (field: keyof typeof call) => {
    const c = call[field]
    const p = put[field]
    if (optionSide === 'call') return typeof c === 'number' ? c : null
    if (optionSide === 'put') return typeof p === 'number' ? p : null
    const values = [c, p].filter((v): v is number => typeof v === 'number')
    if (!values.length) return null
    return values.reduce((acc, v) => acc + v, 0) / values.length
  }

  if (indicator === 'iv') return pick('iv')
  if (indicator === 'delta') return pick('delta')
  if (indicator === 'gamma') return pick('gamma')
  if (indicator === 'theta') return pick('theta')
  if (indicator === 'vega') return pick('vega')
  if (indicator === 'oi') {
    const callOi = typeof call.oi === 'number' ? call.oi : 0
    const putOi = typeof put.oi === 'number' ? put.oi : 0
    if (optionSide === 'call') return callOi
    if (optionSide === 'put') return putOi
    return callOi + putOi
  }
  if (indicator === 'pcr') {
    const callVol = typeof call.volume === 'number' ? call.volume : 0
    const putVol = typeof put.volume === 'number' ? put.volume : 0
    if (callVol === 0) return null
    return putVol / callVol
  }
  return null
}

const CHART_HEIGHT = 420

const MonitorPage = () => {
  const [symbol, setSymbol] = useState(DEFAULT_UNDERLYING.toUpperCase())
  const [symbolInput, setSymbolInput] = useState(DEFAULT_UNDERLYING.toUpperCase())
  const [timeframe, setTimeframe] = useState<Timeframe>('5')
  const [indicators, setIndicators] = useState<FoIndicatorDefinition[]>([])
  const [panelState, setPanelState] = useState<Record<string, PanelViewState>>({})
  const [horizontalOrder, setHorizontalOrder] = useState<string[]>([])
  const [verticalOrder, setVerticalOrder] = useState<string[]>([])
  const [horizontalData, setHorizontalData] = useState<Record<string, FoMoneynessSeries[]>>({})
  const [verticalData, setVerticalData] = useState<Record<string, FoStrikeSeries[]>>({})
  const [expiries, setExpiries] = useState<string[]>([])
  const [selectedExpiries, setSelectedExpiries] = useState<string[]>([])
  const [loadingPanels, setLoadingPanels] = useState(false)
  const [foConnectionStatus, setFoConnectionStatus] = useState<'connected' | 'disconnected'>('disconnected')
  const [monitorConnectionStatus, setMonitorConnectionStatus] = useState<'connected' | 'disconnected'>('disconnected')
  const [metadata, setMetadata] = useState<MonitorMetadataResponse | null>(null)
  const [metadataLoading, setMetadataLoading] = useState<boolean>(true)
  const [metadataError, setMetadataError] = useState<string | null>(null)
  const [strikeGap, setStrikeGap] = useState<number>(DEFAULT_STRIKE_GAP)
  const [sessionStatus, setSessionStatus] = useState<'idle' | 'subscribing' | 'active' | 'error'>('idle')
  const [sessionError, setSessionError] = useState<string | null>(null)
  const [sessionTokens, setSessionTokens] = useState<number[]>([])
  const [latestUnderlying, setLatestUnderlying] = useState<number | null>(null)
  const [searchResults, setSearchResults] = useState<MonitorSearchResult[]>([])
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [showDerivativesPopup, setShowDerivativesPopup] = useState<{
    underlying: string
    strike?: number
    bucket?: string
    expiry: string
    timestamp: number
  } | null>(null)
  const horizontalLoadIdRef = useRef(0)
  const verticalLoadIdRef = useRef(0)
  const sessionIdRef = useRef<string | null>(null)
  const canonicalSymbol = useMemo(() => displayUnderlyingSymbol(symbol), [symbol])
  const backendSymbol = useMemo(() => normalizeUnderlyingSymbol(symbol), [symbol])

  // Sprint 3: Replay mode and performance mode
  const [performanceMode, setPerformanceMode] = useState(false)

  // Collect panel IDs for replay mode
  const activePanelIds = useMemo(() => {
    const ids: string[] = []
    Object.entries(panelState).forEach(([id, state]) => {
      if (state.enabled) {
        const indicator = indicators.find(ind => ind.id === id)
        if (indicator) {
          ids.push(`${indicator.option_side}_${indicator.indicator}`)
        }
      }
    })
    return ids
  }, [panelState, indicators])

  const { state: replayState, controls: replayControls, speedPresets } = useReplayMode(
    canonicalSymbol,
    `${timeframe}min`,
    selectedExpiries,
    activePanelIds
  )

  const extractPrice = useCallback((payload: Record<string, unknown> | null | undefined): number | null => {
    if (!payload || typeof payload !== 'object') return null
    const candidates = ['close', 'price', 'last_price', 'ltp']
    for (const field of candidates) {
      const value = (payload as Record<string, unknown>)[field]
      const numeric = typeof value === 'number' ? value : typeof value === 'string' ? Number(value) : NaN
      if (!Number.isNaN(numeric)) return numeric
    }
    return null
  }, [])

  const classifyBucket = useCallback((strike: number, underlying?: number | null): string => {
    if (strikeGap <= 0 || underlying == null) return 'ATM'
    const level = Math.round((strike - underlying) / strikeGap)
    if (level === 0) return 'ATM'
    const prefix = level > 0 ? 'OTM' : 'ITM'
    return `${prefix}${Math.abs(level)}`
  }, [strikeGap])

  useEffect(() => {
    fetchFoIndicators().then(defs => {
      if (!Array.isArray(defs)) {
        console.warn('fetchFoIndicators returned non-array:', defs);
        setIndicators([]);
        return;
      }
      setIndicators(defs)
      const nextState: Record<string, PanelViewState> = {}
      const horizontal: string[] = []
      const vertical: string[] = []
      defs.forEach(def => {
        nextState[def.id] = { enabled: def.default, collapsed: false }
        if (def.orientation === 'horizontal') horizontal.push(def.id)
        else vertical.push(def.id)
      })
      setPanelState(nextState)
      setHorizontalOrder(horizontal)
      setVerticalOrder(vertical)
    }).catch(error => {
      console.error('Failed to fetch indicators:', error);
      setIndicators([]); // Ensure we have an empty array
    })
  }, [])

  useEffect(() => {
    if (!backendSymbol) {
      setMetadata(null)
      setMetadataLoading(false)
      return
    }
    let cancelled = false
    setMetadataLoading(true)
    fetchMonitorMetadata({ symbol: backendSymbol })
      .then(resp => {
        if (cancelled) return
        setMetadata(resp)
        setMetadataError(null)
        setStrikeGap(resp.meta?.strike_gap ?? DEFAULT_STRIKE_GAP)
        const expiryList = resp.options.map(option => option.expiry)
        setExpiries(expiryList)
        console.log('[MonitorPage] Setting expiries:', expiryList)
        setSelectedExpiries(prev => {
          const preserved = prev.filter(expiry => expiryList.includes(expiry))
          if (preserved.length) {
            console.log('[MonitorPage] Preserving selected expiries:', preserved)
            return preserved
          }
          const autoSelected = expiryList.slice(0, Math.min(3, expiryList.length))
          console.log('[MonitorPage] Auto-selecting first 3 expiries:', autoSelected)
          return autoSelected
        })
        if (resp.underlying?.last_price != null) {
          setLatestUnderlying(resp.underlying.last_price)
        }
        const responseSymbol = displayUnderlyingSymbol(resp.symbol || symbol)
        if (responseSymbol && responseSymbol !== symbol) {
          setSymbol(responseSymbol)
          setSymbolInput(responseSymbol)
        }
        setSearchResults([])
        setSearchError(null)
      })
      .catch(err => {
        if (cancelled) return
        const message = err instanceof Error ? err.message : 'Failed to load monitor metadata'
        setMetadataError(message)
        setMetadata(null)
        setExpiries([])
        setSelectedExpiries([])
      })
      .finally(() => {
        if (!cancelled) setMetadataLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [backendSymbol, symbol])

  useEffect(() => {
    const query = symbolInput.trim()
    if (!query || query.length < 2) {
      setSearchResults([])
      setSearchLoading(false)
      setSearchError(null)
      return
    }
    if (normalizeUnderlyingSymbol(query) === backendSymbol) {
      setSearchResults([])
      setSearchLoading(false)
      setSearchError(null)
      return
    }

    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => {
      setSearchLoading(true)
      setSearchError(null)
      searchMonitorSymbols(query, 15, controller.signal)
        .then(results => {
          setSearchResults(results)
          setSearchError(null)
        })
        .catch(err => {
          if ((err as { code?: string }).code === 'ERR_CANCELED') {
            return
          }
          setSearchResults([])
          setSearchError(err instanceof Error ? err.message : 'Search failed')
        })
        .finally(() => {
          setSearchLoading(false)
        })
    }, 250)

    return () => {
      controller.abort()
      window.clearTimeout(timeoutId)
    }
  }, [symbolInput, backendSymbol])

  const tokensForSession = useMemo(() => {
    if (!metadata) return []
    const tokens = new Set<number>()
    const addToken = (leg?: { instrument_token?: number | null } | null) => {
      const token = leg?.instrument_token
      if (typeof token === 'number') {
        tokens.add(token)
      }
    }
    addToken(metadata.underlying)
    metadata.futures.forEach(addToken)
    metadata.options.forEach(expiry => {
      expiry.strikes.forEach(strike => {
        addToken(strike.call)
        addToken(strike.put)
      })
    })
    return Array.from(tokens)
  }, [metadata])

  useEffect(() => {
    if (!tokensForSession.length) {
      if (sessionIdRef.current) {
        const sessionId = sessionIdRef.current
        deleteMonitorSession(sessionId).catch(() => {})
        sessionIdRef.current = null
      }
      setSessionTokens([])
      setSessionStatus('idle')
      setSessionError(null)
      return
    }
    let cancelled = false
    const establishSession = async () => {
      setSessionStatus('subscribing')
      try {
        if (sessionIdRef.current) {
          const existing = sessionIdRef.current
          sessionIdRef.current = null
          await deleteMonitorSession(existing).catch(() => {})
        }
        const response = await createMonitorSession({ tokens: tokensForSession })
        if (cancelled) {
          await deleteMonitorSession(response.session_id).catch(() => {})
          return
        }
        sessionIdRef.current = response.session_id
        setSessionTokens(response.tokens)
        setSessionStatus('active')
        setSessionError(null)
      } catch (err) {
        if (cancelled) return
        setSessionStatus('error')
        const message = err instanceof Error ? err.message : 'Failed to start ticker session'
        setSessionError(message)
      }
    }
    establishSession()
    return () => {
      cancelled = true
    }
  }, [tokensForSession])

  const activeHorizontalPanels = useMemo(
    () => (indicators || []).filter(def => def.orientation === 'horizontal' && panelState[def.id]?.enabled),
    [indicators, panelState]
  )
  const activeVerticalPanels = useMemo(
    () => (indicators || []).filter(def => def.orientation === 'vertical' && panelState[def.id]?.enabled),
    [indicators, panelState]
  )

  const colorMap = useMemo(() => {
    const map: Record<string, string> = {}
    selectedExpiries.forEach((expiry, idx) => {
      map[expiry] = COLORS[idx % COLORS.length]
    })
    return map
  }, [selectedExpiries])

  useEffect(() => {
    return () => {
      const sessionId = sessionIdRef.current
      if (sessionId) {
        deleteMonitorSession(sessionId).catch(() => {})
      }
    }
  }, [])

  useEffect(() => {
    if (!metadata || !backendSymbol) return
    let cancelled = false
    fetchMonitorSnapshot({ symbol: backendSymbol, timeframe })
      .then(resp => {
        if (cancelled) return
        const price = extractPrice(resp.underlying ?? null)
        if (price != null) setLatestUnderlying(price)
      })
      .catch(() => {
        /* snapshot optional */
      })
    return () => {
      cancelled = true
    }
  }, [metadata, extractPrice, backendSymbol, timeframe])

  useEffect(() => {
    if (!metadata) return
    const ws = connectMonitorStream()
    ws.onopen = () => setMonitorConnectionStatus('connected')
    ws.onclose = () => setMonitorConnectionStatus('disconnected')
    ws.onerror = () => setMonitorConnectionStatus('disconnected')
    ws.onmessage = event => {
      try {
        // Skip non-JSON messages like "ping"
        if (typeof event.data !== 'string' || !event.data.startsWith('{')) {
          return
        }
        const message: MonitorStreamMessage = JSON.parse(event.data)
        if (!message || typeof message !== 'object') return
        const channel = message.channel
        if (channel === metadata.meta?.redis_channels?.underlying) {
          const price = extractPrice(message.payload)
          if (price != null) setLatestUnderlying(price)
        }
      } catch (err) {
        console.error('Failed to parse monitor stream payload', err)
      }
    }
    return () => ws.close()
  }, [metadata, extractPrice])

  const loadHorizontalPanels = useCallback(async () => {
    const loadId = ++horizontalLoadIdRef.current
    if (!selectedExpiries.length || !activeHorizontalPanels.length) {
      if (loadId === horizontalLoadIdRef.current) {
        setHorizontalData({})
        setLoadingPanels(false)
      }
      return
    }
    setLoadingPanels(true)
    const entries = await Promise.all(activeHorizontalPanels.map(async panel => {
      const resp = await fetchFoMoneynessSeries({
        symbol,
        timeframe,
        indicator: panel.indicator,
        option_side: panel.option_side,
        expiry: selectedExpiries,
      })
      return [panel.id, resp.series] as const
    }))
    if (loadId !== horizontalLoadIdRef.current) return
    setHorizontalData(Object.fromEntries(entries))
    setLoadingPanels(false)
  }, [activeHorizontalPanels, selectedExpiries, symbol, timeframe])

  const loadVerticalPanels = useCallback(async () => {
    const loadId = ++verticalLoadIdRef.current
    console.log('[MonitorPage] loadVerticalPanels called:', {
      selectedExpiries: selectedExpiries.length,
      activeVerticalPanels: activeVerticalPanels.length,
      symbol,
      timeframe
    })
    if (!selectedExpiries.length || !activeVerticalPanels.length) {
      console.log('[MonitorPage] Skipping vertical panel load - no expiries or panels selected')
      if (loadId === verticalLoadIdRef.current) {
        setVerticalData({})
      }
      return
    }
    console.log('[MonitorPage] Fetching vertical panel data for expiries:', selectedExpiries)
    const entries = await Promise.all(activeVerticalPanels.map(async panel => {
      console.log(`[MonitorPage] Fetching ${panel.indicator} for panel ${panel.id}`)
      try {
        const resp = await fetchFoStrikeDistribution({
          symbol,
          timeframe,
          indicator: panel.indicator,
          expiry: selectedExpiries,
        })
        console.log(`[MonitorPage] Received ${resp.series.length} series for panel ${panel.id}`)
        return [panel.id, resp.series] as const
      } catch (error) {
        console.error(`[MonitorPage] Failed to fetch ${panel.id}:`, error)
        return [panel.id, []] as const
      }
    }))
    if (loadId !== verticalLoadIdRef.current) return
    console.log('[MonitorPage] Setting vertical data:', Object.fromEntries(entries.map(([id, series]) => [id, series.length])))
    setVerticalData(Object.fromEntries(entries))
  }, [activeVerticalPanels, selectedExpiries, symbol, timeframe])

  useEffect(() => {
    loadHorizontalPanels()
    loadVerticalPanels()
  }, [loadHorizontalPanels, loadVerticalPanels])

  useEffect(() => {
    const ws = connectFoStream()
    ws.onopen = () => setFoConnectionStatus('connected')
    ws.onclose = () => setFoConnectionStatus('disconnected')
    ws.onerror = () => setFoConnectionStatus('disconnected')
    ws.onmessage = (event) => {
      try {
        // Skip non-JSON messages like "ping"
        if (typeof event.data !== 'string' || !event.data.startsWith('{')) {
          return
        }
        const payload: FoRealtimeBucket = JSON.parse(event.data)
        if (payload.type !== 'fo_bucket') return
        if (payload.timeframe !== timeframe) return
        if (normalizeUnderlyingSymbol(payload.symbol ?? '') !== backendSymbol) return
        if (!selectedExpiries.includes(payload.expiry)) return
        setHorizontalData(prev => {
          const next = { ...prev }
          activeHorizontalPanels.forEach(panel => {
            payload.strikes.forEach(strikeEntry => {
              const value = aggregateRealtimeValue(panel.indicator, panel.option_side, strikeEntry)
              if (value == null) return
              const bucket = classifyBucket(strikeEntry.strike, strikeEntry.underlying)
              const point = { time: payload.bucket_time, value }
              if (!next[panel.id]) next[panel.id] = []
              const existingSeries = next[panel.id].find(series => series.expiry === payload.expiry && series.bucket === bucket)
              if (existingSeries) {
                existingSeries.points = [...existingSeries.points.filter(p => p.time !== point.time), point]
              } else {
                next[panel.id] = [...next[panel.id], { expiry: payload.expiry, bucket, points: [point] }]
              }
            })
          })
          return next
        })
        setVerticalData(prev => {
          const next = { ...prev }
          activeVerticalPanels.forEach(panel => {
            payload.strikes.forEach(strikeEntry => {
              const value = aggregateRealtimeValue(panel.indicator, panel.option_side, strikeEntry)
              if (value == null) return
              const field = REALTIME_FIELD_MAP[panel.indicator as keyof typeof REALTIME_FIELD_MAP] ?? null
              const point = {
                strike: strikeEntry.strike,
                value,
                call: field ? (strikeEntry.call?.[field] ?? null) : null,
                put: field ? (strikeEntry.put?.[field] ?? null) : null,
                call_oi: strikeEntry.call?.oi ?? null,
                put_oi: strikeEntry.put?.oi ?? null,
                bucket_time: payload.bucket_time,
                underlying: strikeEntry.underlying,
              }
              if (!next[panel.id]) next[panel.id] = []
              const series = next[panel.id].find(s => s.expiry === payload.expiry)
              if (series) {
                const existingPoints = series.points ?? []
                series.points = [...existingPoints.filter(p => p.strike !== point.strike), point]
              } else {
                next[panel.id] = [
                  ...next[panel.id],
                  { expiry: payload.expiry, bucket_time: payload.bucket_time, points: [point] },
                ]
              }
            })
          })
          return next
        })
      } catch (err) {
        console.error('Failed to parse FO stream payload', err)
      }
    }
    return () => ws.close()
  }, [timeframe, selectedExpiries, activeHorizontalPanels, activeVerticalPanels, classifyBucket, backendSymbol])

  const togglePanel = (id: string) => {
    setPanelState(prev => {
      const current = prev[id] ?? { enabled: false, collapsed: false }
      return { ...prev, [id]: { ...current, enabled: !current.enabled } }
    })
  }

  const toggleCollapse = (id: string) => {
    setPanelState(prev => {
      const current = prev[id] ?? { enabled: true, collapsed: false }
      return { ...prev, [id]: { ...current, collapsed: !current.collapsed } }
    })
  }

  const movePanel = (orientation: 'horizontal' | 'vertical', id: string, direction: 'up' | 'down') => {
    const order = orientation === 'horizontal' ? horizontalOrder : verticalOrder
    const index = order.indexOf(id)
    if (index === -1) return
    const nextIndex = direction === 'up' ? index - 1 : index + 1
    if (nextIndex < 0 || nextIndex >= order.length) return
    const newOrder = [...order]
    const tmp = newOrder[index]
    newOrder[index] = newOrder[nextIndex]
    newOrder[nextIndex] = tmp
    if (orientation === 'horizontal') setHorizontalOrder(newOrder)
    else setVerticalOrder(newOrder)
  }

  const handleExpirySelect = (expiry: string) => {
    setSelectedExpiries(prev => prev.includes(expiry) ? prev.filter(e => e !== expiry) : [...prev, expiry])
  }

  const handleSearchSelect = (result: MonitorSearchResult) => {
    const resolvedSymbol = result.canonical_symbol || result.display_symbol || ''
    const display = displayUnderlyingSymbol(resolvedSymbol)
    setSymbol(display || resolvedSymbol.toUpperCase())
    setSymbolInput(display || resolvedSymbol.toUpperCase())
    setSearchResults([])
    setSearchError(null)
  }

  const handleSymbolSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const next = symbolInput.trim()
    if (!next) return
    const normalizedInput = displayUnderlyingSymbol(next)
    const backendInput = normalizeUnderlyingSymbol(next)
    const directMatch = searchResults.find(result => {
      const display = result.display_symbol || ''
      const resultBackend = normalizeUnderlyingSymbol(result.canonical_symbol || '')
      const resultDisplay = displayUnderlyingSymbol(display)
      return (
        (!!resultBackend && resultBackend === backendInput) ||
        resultDisplay === normalizedInput ||
        display.toUpperCase() === next.toUpperCase()
      )
    })
    if (directMatch) {
      handleSearchSelect(directMatch)
      return
    }
    const displayValue = normalizedInput || next.toUpperCase()
    setSymbol(displayValue)
    setSymbolInput(displayValue)
    setSearchResults([])
    setSearchError(null)
  }

  // Handler for horizontal panel Show Chart
  const handleHorizontalPanelShowChart = useCallback((context: { bucket: string; expiry: string; timestamp: number; underlying: string }) => {
    setShowDerivativesPopup({
      underlying: context.underlying,
      bucket: context.bucket,
      expiry: context.expiry,
      timestamp: context.timestamp
    })
  }, [])

  // Handler for vertical panel Show Chart
  const handleVerticalPanelShowChart = useCallback((context: { strike: number; expiry: string; timestamp: number; underlying: string }) => {
    setShowDerivativesPopup({
      underlying: context.underlying,
      strike: context.strike,
      expiry: context.expiry,
      timestamp: context.timestamp
    })
  }, [])

  // Handler for popup pin state
  const handlePopupPin = useCallback(async (pinnedState: any) => {
    console.log('Popup pinned with state:', pinnedState)

    if (!showDerivativesPopup) return

    try {
      // Import labels service
      const { createLabel } = await import('../services/labels')

      // Create a label with pinned cursor state
      const label = await createLabel({
        symbol: showDerivativesPopup.underlying,
        label_type: 'neutral',
        metadata: {
          timeframe: timeframe + 'm',
          nearest_candle_timestamp_utc: new Date(showDerivativesPopup.timestamp * 1000).toISOString(),
          sample_offset_seconds: 0,
          strike: showDerivativesPopup.strike,
          bucket: showDerivativesPopup.bucket,
          pinnedCursorState: pinnedState
        },
        tags: ['pinned', 'popup']
      })

      console.log('Pinned state saved to label:', label.id)
    } catch (error) {
      console.error('Failed to save pinned state:', error)
    }
  }, [showDerivativesPopup, timeframe])

  return (
    <MonitorSyncProvider>
      <div className="monitor-page">
        <header className="monitor-header">
          <div>
            <h1>Market Monitor</h1>
            <p>Historical + real-time derivatives overview</p>
          </div>
          <div className="monitor-header__controls">
            <form className="monitor-symbol-form" onSubmit={handleSymbolSubmit}>
              <label htmlFor="monitor-symbol-input">Underlying</label>
              <input
                id="monitor-symbol-input"
                value={symbolInput}
                onChange={event => setSymbolInput(event.target.value)}
                placeholder="e.g. NIFTY, BANKNIFTY"
              />
              <button type="submit">Apply</button>
            </form>
            {symbolInput.trim().length >= 2 && (
              <div className="monitor-symbol-results">
                {searchLoading && <div className="monitor-chip">Searching…</div>}
                {!searchLoading && searchError && (
                  <div className="monitor-chip monitor-chip--error">{searchError}</div>
                )}
                {!searchLoading && !searchError && searchResults.length > 0 && (
                  <div className="monitor-symbol-results__list">
                    {searchResults.slice(0, 6).map(result => (
                      <button
                        key={`${result.canonical_symbol}-${result.instrument_token ?? 'na'}`}
                        type="button"
                        className="monitor-symbol-option"
                        onClick={() => handleSearchSelect(result)}
                      >
                        <strong>{result.display_symbol}</strong>{' '}
                        {result.name && <span className="monitor-symbol-option__name">({result.name})</span>}
                        {result.exchange && <span className="monitor-symbol-option__meta"> · {result.exchange}</span>}
                      </button>
                    ))}
                  </div>
                )}
                {!searchLoading && !searchError && !searchResults.length && (
                  <div className="monitor-chip">No matches</div>
                )}
              </div>
            )}
            <div className="monitor-chip">Symbol: {metadata?.symbol ?? canonicalSymbol ?? symbol}</div>
            {latestUnderlying != null && (
              <div className="monitor-chip">Underlying: {latestUnderlying.toFixed(2)}</div>
            )}
            <div className="monitor-chip monitor-chip--status">
              FO Stream: {foConnectionStatus === 'connected' ? 'Live' : 'Offline'}
            </div>
            <div className="monitor-chip monitor-chip--status">
              Ticker Stream: {monitorConnectionStatus === 'connected' ? 'Live' : 'Offline'}
            </div>
            <div className="monitor-chip">
              Session: {sessionStatus === 'active'
                ? `Active (${sessionTokens.length})`
                : sessionStatus === 'error'
                  ? 'Error'
                  : sessionStatus === 'subscribing'
                    ? 'Starting…'
                    : 'Idle'}
            </div>

            {/* Sprint 3: Replay Mode Button */}
            <button
              className="monitor-chip"
              style={{ cursor: 'pointer', fontWeight: replayState.isActive ? '600' : '400' }}
              onClick={replayState.isActive ? replayControls.exit : replayControls.enter}
              title={replayState.isActive ? 'Exit Replay Mode' : 'Enter Replay Mode'}
            >
              {replayState.isActive ? '⏸ Replay Active' : '▶️ Replay'}
            </button>

            {/* Sprint 3: Performance Mode Toggle */}
            <button
              className={performanceMode ? 'perf-mode-toggle perf-mode-toggle--active' : 'perf-mode-toggle'}
              onClick={() => setPerformanceMode(!performanceMode)}
              title={performanceMode ? 'Disable Performance Mode' : 'Enable Performance Mode'}
            >
              {performanceMode ? '⚡ Performance ON' : '🎯 Full Quality'}
            </button>

            <div className="monitor-timeframes">
              {TIMEFRAMES.map(tf => (
                <button
                  key={tf}
                  className={tf === timeframe ? 'active' : ''}
                  type="button"
                  onClick={() => setTimeframe(tf)}
                >
                  {tf === '60' ? '1h' : tf === '1D' ? '1D' : `${tf}m`}
                </button>
              ))}
            </div>
          </div>
        </header>
        <ResizableSplit
          className="monitor-body"
          initialPrimaryPercentage={68}
          minPrimaryPx={720}
          minSecondaryPx={320}
          primary={
            <div className="monitor-left">
              {metadataLoading && (
                <div className="monitor-loading" style={{ marginBottom: 12 }}>
                  Loading ticker metadata…
                </div>
              )}
              {metadataError && (
                <div style={{ marginBottom: 12, color: '#ef4444' }}>
                  {metadataError}
                </div>
              )}
              {sessionError && (
                <div style={{ marginBottom: 12, color: '#ef4444' }}>
                  {sessionError}
                </div>
              )}

              <div className="monitor-left-duplicate">
                <div className="monitor-left-duplicate__frame">
                  <UnderlyingChart symbol={symbol} timeframe={timeframe} />
                </div>
              </div>

              <div className="monitor-filter">
                <label>Expiries</label>
                <div className="monitor-expiries">
                  {expiries.map(exp => (
                    <button
                      key={exp}
                      className={selectedExpiries.includes(exp) ? 'active' : ''}
                      onClick={() => handleExpirySelect(exp)}
                    >
                      {exp}
                    </button>
                  ))}
                </div>
                {!selectedExpiries.length && (
                  <div className="monitor-card__subtext" style={{ marginTop: 8 }}>
                    Select at least one expiry to populate the panels.
                  </div>
                )}
              </div>

              <div className="monitor-main" style={{ position: 'relative' }}>
                <div className="monitor-chart-wrapper">
                  {/* Sprint 3: Replay Mode Watermark */}
                  {replayState.isActive && <ReplayWatermark />}

                  <UnderlyingChart symbol={symbol} timeframe={timeframe} />
                </div>
                {verticalOrder.filter(id => panelState[id]?.enabled).length > 0 && (
                  <div className="monitor-vertical-panels" style={{ height: CHART_HEIGHT }}>
                    {verticalOrder.filter(id => panelState[id]?.enabled).map(id => {
                      const def = indicators.find(ind => ind.id === id && ind.orientation === 'vertical')
                      if (!def) return null
                      return (
                        <VerticalPanel
                          key={id}
                          panel={def}
                          data={verticalData[id] ?? []}
                          colorMap={colorMap}
                          collapsed={panelState[id]?.collapsed ?? false}
                          onToggleCollapse={() => toggleCollapse(id)}
                          height={CHART_HEIGHT}
                          onShowChart={handleVerticalPanelShowChart}
                        />
                      )
                    })}
                  </div>
                )}
              </div>

              {loadingPanels && <div className="monitor-loading">Refreshing indicator panels…</div>}

              {horizontalOrder.filter(id => panelState[id]?.enabled).map(id => {
                const def = indicators.find(ind => ind.id === id && ind.orientation === 'horizontal')
                if (!def) return null
                return (
                  <HorizontalPanel
                    key={id}
                    panel={def}
                    data={horizontalData[id] ?? []}
                    colorMap={colorMap}
                    collapsed={panelState[id]?.collapsed ?? false}
                    onToggleCollapse={() => toggleCollapse(id)}
                    onShowChart={handleHorizontalPanelShowChart}
                  />
                )
              })}
            </div>
          }
          secondary={
            <div className="monitor-right">
              <div className="monitor-right-chart">
                <UnderlyingChart symbol={symbol} timeframe={timeframe} />
              </div>
              <PanelManager
                indicators={indicators.filter(i => i.orientation === 'horizontal')}
                state={panelState}
                order={horizontalOrder}
                onToggleEnabled={togglePanel}
                onToggleCollapse={toggleCollapse}
                onMove={(id, dir) => movePanel('horizontal', id, dir)}
                title="Horizontal Panels"
              />
              <PanelManager
                indicators={indicators.filter(i => i.orientation === 'vertical')}
                state={panelState}
                order={verticalOrder}
                onToggleEnabled={togglePanel}
                onToggleCollapse={toggleCollapse}
                onMove={(id, dir) => movePanel('vertical', id, dir)}
                title="Vertical Panels"
              />
            </div>
          }
        />
      </div>
      
      {/* Derivatives Chart Popup */}
      {showDerivativesPopup && (
        <DerivativesChartPopup
          underlying={showDerivativesPopup.underlying}
          strike={showDerivativesPopup.strike}
          bucket={showDerivativesPopup.bucket}
          expiry={showDerivativesPopup.expiry}
          timestamp={showDerivativesPopup.timestamp}
          onClose={() => setShowDerivativesPopup(null)}
          onPin={handlePopupPin}
        />
      )}

      {/* Sprint 3: Replay Mode Controls */}
      {replayState.isActive && (
        <ReplayControls
          controls={replayControls}
          isPlaying={replayState.isPlaying}
          currentSpeed={replayState.playbackSpeed}
          speedPresets={speedPresets}
          cursorTime={replayState.cursorUtc}
          isEndOfData={
            replayState.bufferedData !== null &&
            replayState.cursorUtc !== null &&
            replayState.bufferedData.timestamps.indexOf(replayState.cursorUtc) ===
              replayState.bufferedData.timestamps.length - 1
          }
        />
      )}
    </MonitorSyncProvider>
  )
}

export default MonitorPage
