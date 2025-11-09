import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { createChart, type IChartApi, type ISeriesApi, type CandlestickData, type Time, type MouseEventParams, type Range, type BusinessDay } from 'lightweight-charts'
import { useMonitorSync } from './MonitorSyncContext'
import { ChartLabels, type ChartContextMenuAction } from '../chart-labels/ChartLabels'
import { ErrorBoundary } from '../ErrorBoundary'
import { Label } from '../../types/labels'
import ShowChartPopup from '../ShowChartPopup/DerivativesChartPopup'
import {
  createLabel,
  deleteLabel,
  fetchLabels,
  connectLabelStream,
  subscribeLabelStream,
  parseLabelMessage,
  timestampToUTC
} from '../../services/labels'
import {
  fetchMonitorMetadata,
  createMonitorSession,
  deleteMonitorSession,
  connectMonitorStream,
  fetchMonitorSnapshot,
} from '../../services/monitor'
import type { MonitorMetadataResponse, MonitorStreamMessage } from '../../types'
import { normalizeUnderlyingSymbol } from '../../utils/symbols'

type Timeframe = '1' | '2' | '3' | '5' | '15' | '30' | '60' | '1D'

export type UnderlyingContextAction =
  | {
      kind: 'copy'
      symbol: string
      timeframe: Timeframe
      timestamp: number | null
      price: number | null
    }
  | {
      kind: 'alerts'
      symbol: string
      timeframe: Timeframe
      timestamp: number | null
      price: number | null
    }
  | {
      kind: 'show-chart'
      variant: 'call-strike' | 'put-strike' | 'straddle-strike'
      symbol: string
      timeframe: Timeframe
      timestamp: number | null
      price: number | null
    }

export interface UnderlyingChartProps {
  symbol: string
  timeframe: Timeframe
  surfaceId?: string
  reportDimensions?: boolean
  enableRealtime?: boolean
  onContextAction?: (action: UnderlyingContextAction) => void
}

interface Bar {
  time: number
  open: number
  high: number
  low: number
  close: number
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/tradingview-api'
const CHART_HEIGHT = 420

const toEpochSeconds = (value: Time): number => {
  if (typeof value === 'number') return value
  if (typeof value === 'string') return Math.floor(new Date(value).getTime() / 1000)
  const date = value as BusinessDay
  return Math.floor(new Date(date.year, date.month - 1, date.day).getTime() / 1000)
}

const fetchBars = async (symbol: string, timeframe: string, from?: number, to?: number): Promise<Bar[]> => {
  const now = Math.floor(Date.now() / 1000)
  const defaultFrom = now - 7 * 24 * 3600
  const params = new URLSearchParams({
    symbol,
    resolution: timeframe,
    from: String(from ?? defaultFrom),
    to: String(to ?? now),
  })
  const res = await fetch(`${API_BASE_URL}/history?${params.toString()}`, { cache: 'no-store' })
  if (!res.ok) return []
  const json = await res.json()
  if (!json || json.s !== 'ok') return []
  const bars: Bar[] = []
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

const toCandle = (bar: Bar): CandlestickData => ({
  time: bar.time as Time,
  open: bar.open,
  high: bar.high,
  low: bar.low,
  close: bar.close,
})

const timeframeToSeconds = (timeframe: Timeframe): number => {
  switch (timeframe) {
    case '1':
      return 60
    case '2':
      return 120
    case '3':
      return 180
    case '5':
      return 300
    case '15':
      return 900
    case '30':
      return 1800
    case '60':
      return 3600
    case '1D':
    default:
      return 86400
  }
}

const startOfDaySeconds = (epochSeconds: number): number => {
  const date = new Date(epochSeconds * 1000)
  date.setUTCHours(0, 0, 0, 0)
  return Math.floor(date.getTime() / 1000)
}

const normalizeBucketTime = (timestampSeconds: number, timeframe: Timeframe): number => {
  if (timeframe === '1D') {
    return startOfDaySeconds(timestampSeconds)
  }
  const interval = timeframeToSeconds(timeframe)
  return timestampSeconds - (timestampSeconds % interval)
}

const UnderlyingChart = ({
  symbol,
  timeframe,
  surfaceId,
  reportDimensions = false,
  enableRealtime = false,
  onContextAction,
}: UnderlyingChartProps) => {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const lastBarRef = useRef<CandlestickData | null>(null)
  const [loading, setLoading] = useState(false)
  const [labels, setLabels] = useState<Label[]>([])
  const [showChartPopup, setShowChartPopup] = useState<{
    underlying: string
    strike: number
    timestamp: string
    expiry: string
  } | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const monitorWsRef = useRef<WebSocket | null>(null)
  const sessionIdRef = useRef<string | null>(null)
  const snapshotIntervalRef = useRef<number | null>(null)
  const streamConnectedRef = useRef(false)
  const reconnectAttemptsRef = useRef(0)
  const lastStreamUpdateRef = useRef<number>(0)
  const lastStreamErrorRef = useRef<number>(0)
  const [metadata, setMetadata] = useState<MonitorMetadataResponse | null>(null)
  const {
    setTimeRange,
    setCrosshairTime,
    setPriceRange,
    setCrosshairRatio,
    setCrosshairWidth,
    setCrosshairPrice,
  } = useMonitorSync()

  const syncPriceRange = useCallback(() => {
    const series = seriesRef.current
    if (!series) return
    try {
      const top = series.coordinateToPrice(0)
      const bottom = series.coordinateToPrice(CHART_HEIGHT)
      if (top == null || bottom == null) return
      setPriceRange({ min: Math.min(top, bottom), max: Math.max(top, bottom) })
    } catch (err) {
      // series might be disposed while the chart is recreating
    }
  }, [setPriceRange])

  const extractPrice = useCallback((payload: Record<string, unknown> | null | undefined): number | null => {
    if (!payload || typeof payload !== 'object') return null
    const candidates = ['close', 'price', 'last_price', 'ltp', 'trade_price']
    for (const field of candidates) {
      const value = (payload as Record<string, unknown>)[field]
      const numeric = typeof value === 'number' ? value : typeof value === 'string' ? Number(value) : NaN
      if (!Number.isNaN(numeric)) return numeric
    }
    return null
  }, [])

  const extractTimestamp = useCallback((payload: Record<string, unknown> | null | undefined): number => {
    if (!payload || typeof payload !== 'object') return Math.floor(Date.now() / 1000)
    const candidates = ['timestamp', 'time', 'ts', 'exchange_timestamp', 'last_trade_time']
    for (const field of candidates) {
      const value = (payload as Record<string, unknown>)[field]
      if (typeof value === 'number' && Number.isFinite(value)) {
        return value > 1e12 ? Math.floor(value / 1000) : Math.floor(value)
      }
      if (typeof value === 'string') {
        const parsed = Number(value)
        if (!Number.isNaN(parsed)) {
          return parsed > 1e12 ? Math.floor(parsed / 1000) : Math.floor(parsed)
        }
      }
    }
    return Math.floor(Date.now() / 1000)
  }, [])

  const updateRealtimeBar = useCallback(
    (price: number, timestampSeconds: number) => {
      const series = seriesRef.current
      if (!series || !Number.isFinite(price)) return
      const bucketTime = normalizeBucketTime(timestampSeconds, timeframe)
      const interval = timeframeToSeconds(timeframe)
      const lastBar = lastBarRef.current
      const lastBarTime = lastBar ? toEpochSeconds(lastBar.time) : null

      if (lastBarTime != null && bucketTime < lastBarTime) {
        // Lightweight charts throws if we try to update with an older bucket, so ignore stale ticks
        return
      }

      if (lastBar && lastBarTime === bucketTime) {
        const updated: CandlestickData = {
          ...lastBar,
          close: price,
          high: Math.max(lastBar.high, price),
          low: Math.min(lastBar.low, price),
        }
        lastBarRef.current = updated
        series.update(updated)
        return
      }

      const previousClose = lastBar?.close ?? price
      const newBar: CandlestickData = {
        time: bucketTime as Time,
        open:
          lastBar && lastBarTime != null && bucketTime - lastBarTime <= interval ? lastBar.close : price,
        high: Math.max(previousClose, price),
        low: Math.min(previousClose, price),
        close: price,
      }
      lastBarRef.current = newBar
      series.update(newBar)
    },
    [timeframe],
  )

  useEffect(() => {
    lastBarRef.current = null
    lastStreamUpdateRef.current = 0
  }, [symbol, timeframe])

  // Label handlers
  const handleLabelCreate = useCallback(async (timestamp: number, labelType: Label['label_type']) => {
    try {
      const response = await createLabel({
        symbol,
        label_type: labelType,
        metadata: {
          timeframe,
          nearest_candle_timestamp_utc: timestampToUTC(timestamp),
          sample_offset_seconds: 0
        },
        tags: ['manual']
      });
      console.log('Label created:', response);
    } catch (error) {
      console.error('Failed to create label:', error);
    }
  }, [symbol, timeframe]);

  const handleLabelUpdate = useCallback(async (labelId: string, updates: Partial<Label>) => {
    try {
      // Update logic will be implemented in Sprint 2
      console.log('Label update requested:', labelId, updates);
    } catch (error) {
      console.error('Failed to update label:', error);
    }
  }, []);

  const handleLabelDelete = useCallback(async (labelId: string) => {
    try {
      const label = labels.find(l => l.id === labelId);
      if (!label) return;

      const timestamp = new Date(label.metadata.nearest_candle_timestamp_utc).getTime() / 1000;
      await deleteLabel(labelId, symbol, timeframe, timestamp);

      // Remove from local state optimistically
      setLabels(prev => prev.filter(l => l.id !== labelId));
    } catch (error) {
      console.error('Failed to delete label:', error);
    }
  }, [labels, symbol, timeframe]);

  const handleShowChart = useCallback((labelId: string) => {
    const label = labels.find(l => l.id === labelId);
    if (!label) return;

    // Extract metadata from label
    const timestamp = label.metadata.nearest_candle_timestamp_utc;
    const expiry = (label.metadata as any).expiry || '2025-11-27'; // Default expiry
    const strike = (label.metadata as any).strike || 24000; // Default strike based on NIFTY

    setShowChartPopup({
      underlying: symbol,
      strike,
      timestamp,
      expiry
    });
  }, [labels, symbol]);

  const backendSymbol = useMemo(() => normalizeUnderlyingSymbol(symbol), [symbol])

  useEffect(() => {
    if (!containerRef.current) return
    chartRef.current?.remove()
    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: '#0e1117' },
        textColor: '#d1d4dc',
      },
      grid: {
        vertLines: { color: '#1f242c' },
        horzLines: { color: '#1f242c' },
      },
      crosshair: {
        mode: 1,
        vertLine: {
          color: '#26a69a',
          width: 1,
          labelBackgroundColor: '#1e222d',
        },
        horzLine: {
          color: '#26a69a',
          width: 1,
          labelBackgroundColor: '#1e222d',
        },
      },
      localization: {
        timeFormatter: (time: number) => new Date(time * 1000).toLocaleString('en-IN', {
          hour: '2-digit',
          minute: '2-digit',
          day: '2-digit',
          month: 'short',
          timeZone: 'Asia/Kolkata',
          hour12: false,
        }),
      },
      width: containerRef.current.clientWidth,
      height: CHART_HEIGHT,
    })
    const series = chart.addCandlestickSeries({
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    })
    chartRef.current = chart
    seriesRef.current = series

    const updateDimensions = () => {
      const width = containerRef.current?.clientWidth ?? 0
      chart.applyOptions({ width: width || 800 })
      if (reportDimensions) {
        setCrosshairWidth(width || null)
      }
    }
    updateDimensions()
    window.addEventListener('resize', updateDimensions)

    let resizeObserver: ResizeObserver | null = null
    if (typeof ResizeObserver !== 'undefined' && containerRef.current) {
      resizeObserver = new ResizeObserver(() => updateDimensions())
      resizeObserver.observe(containerRef.current)
    }

    const handleTimeRange = (range: Range<Time> | null) => {
      if (range) {
        setTimeRange({ from: toEpochSeconds(range.from), to: toEpochSeconds(range.to) })
      }
      syncPriceRange()
    }
    chart.timeScale().subscribeVisibleTimeRangeChange(handleTimeRange)

    const handleCrosshair = (param: MouseEventParams<Time>) => {
      if (param.time) {
        setCrosshairTime(Number(param.time))
      } else {
        setCrosshairTime(null)
      }

      if (param.point && containerRef.current) {
        const width = containerRef.current.clientWidth || 1
        const ratio = Math.min(Math.max(param.point.x / width, 0), 1)
        setCrosshairRatio(ratio)
        if (seriesRef.current) {
          const maybePrice = seriesRef.current.coordinateToPrice(param.point.y)
          if (typeof maybePrice === 'number' && Number.isFinite(maybePrice)) {
            setCrosshairPrice(maybePrice)
          } else {
            setCrosshairPrice(null)
          }
        }
      } else {
        setCrosshairRatio(null)
        setCrosshairPrice(null)
      }

      syncPriceRange()
    }
    chart.subscribeCrosshairMove(handleCrosshair)

    const container = containerRef.current
    const handleWheel = () => syncPriceRange()
    const handleMouseUp = () => syncPriceRange()
    container?.addEventListener('wheel', handleWheel)
    container?.addEventListener('mouseup', handleMouseUp)

    return () => {
      window.removeEventListener('resize', updateDimensions)
      resizeObserver?.disconnect()
      chart.timeScale().unsubscribeVisibleTimeRangeChange(handleTimeRange)
      chart.unsubscribeCrosshairMove(handleCrosshair)
      container?.removeEventListener('wheel', handleWheel)
      container?.removeEventListener('mouseup', handleMouseUp)
      setCrosshairRatio(null)
      setCrosshairPrice(null)
      if (reportDimensions) {
        setCrosshairWidth(null)
      }
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
    }
  }, [
    symbol,
    timeframe,
    reportDimensions,
    setTimeRange,
    setCrosshairTime,
    setCrosshairRatio,
    setCrosshairWidth,
    setCrosshairPrice,
    syncPriceRange,
  ])

  useEffect(() => {
    const load = async () => {
      if (!seriesRef.current) return
      setLoading(true)
      const bars = await fetchBars(symbol, timeframe)
      const candles = bars.map(toCandle)
      seriesRef.current.setData(candles)
      lastBarRef.current = candles.length ? candles[candles.length - 1] : null
      if (bars.length) {
        const highs = bars.map(bar => bar.high)
        const lows = bars.map(bar => bar.low)
        setPriceRange({ min: Math.min(...lows), max: Math.max(...highs) })
        setTimeRange({ from: bars[0].time, to: bars[bars.length - 1].time })
        syncPriceRange()
      }
      setLoading(false)
    }
    load()
  }, [symbol, timeframe, setPriceRange, setTimeRange, syncPriceRange])

  useEffect(() => {
    if (!enableRealtime || !backendSymbol) {
      setMetadata(null)
      return
    }
    let cancelled = false
    fetchMonitorMetadata({ symbol: backendSymbol })
      .then((response) => {
        if (!cancelled) {
          setMetadata(response)
        }
      })
      .catch((error) => {
        console.error('[UnderlyingChart] Failed to load monitor metadata', error)
        if (!cancelled) setMetadata(null)
      })
    return () => {
      cancelled = true
    }
  }, [enableRealtime, backendSymbol])

  useEffect(() => {
    if (!enableRealtime) return
    const token = metadata?.underlying?.instrument_token
    if (!token) return
    let cancelled = false

    const establishSession = async () => {
      try {
        if (sessionIdRef.current) {
          const existing = sessionIdRef.current
          sessionIdRef.current = null
          await deleteMonitorSession(existing).catch(() => undefined)
        }
        const response = await createMonitorSession({ tokens: [token] })
        if (cancelled) {
          await deleteMonitorSession(response.session_id).catch(() => undefined)
          return
        }
        sessionIdRef.current = response.session_id
      } catch (error) {
        if (!cancelled) {
          console.error('[UnderlyingChart] Failed to create monitor session', error)
        }
      }
    }

    establishSession()
    return () => {
      cancelled = true
      const sessionId = sessionIdRef.current
      sessionIdRef.current = null
      if (sessionId) {
        deleteMonitorSession(sessionId).catch(() => undefined)
      }
    }
  }, [enableRealtime, metadata?.underlying?.instrument_token])

  useEffect(() => {
    if (!enableRealtime) return
    const channel = metadata?.meta?.redis_channels?.underlying
    if (!channel) return

    let active = true

    const connectStream = () => {
      if (!active) return
      const ws = connectMonitorStream()
      monitorWsRef.current = ws

      ws.onopen = () => {
        streamConnectedRef.current = true
        reconnectAttemptsRef.current = 0
        lastStreamUpdateRef.current = Date.now()
      }

      ws.onmessage = (event) => {
        try {
          if (typeof event.data !== 'string' || !event.data.startsWith('{')) {
            return
          }
          const message: MonitorStreamMessage = JSON.parse(event.data)
          if (!message || typeof message !== 'object') return
          if (message.channel !== channel) return
          const price = extractPrice(message.payload)
          if (price == null) return
          const timestamp = extractTimestamp(message.payload)
          updateRealtimeBar(price, timestamp)
          lastStreamUpdateRef.current = Date.now()
        } catch (error) {
          console.error('[UnderlyingChart] Failed to process monitor payload', error)
        }
      }

      ws.onerror = (error) => {
        const now = Date.now()
        if (now - lastStreamErrorRef.current > 5000) {
          console.error('[UnderlyingChart] Monitor stream error', error)
          lastStreamErrorRef.current = now
        }
        streamConnectedRef.current = false
        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
          try {
            ws.close()
          } catch (closeError) {
            console.error('[UnderlyingChart] Failed to close monitor stream after error', closeError)
          }
        }
      }

      ws.onclose = () => {
        monitorWsRef.current = null
        streamConnectedRef.current = false
        if (!active) return
        const attempt = (reconnectAttemptsRef.current += 1)
        const retryDelay = Math.min(5000, 500 * attempt)
        window.setTimeout(connectStream, retryDelay)
      }
    }

    connectStream()

    return () => {
      active = false
      streamConnectedRef.current = false
      const ws = monitorWsRef.current
      monitorWsRef.current = null
      if (ws) {
        try {
          ws.close()
        } catch (error) {
          console.error('[UnderlyingChart] Failed to close monitor stream during cleanup', error)
        }
      }
    }
  }, [enableRealtime, metadata?.meta?.redis_channels?.underlying, extractPrice, extractTimestamp, updateRealtimeBar])

  useEffect(() => {
    if (!enableRealtime) {
      if (snapshotIntervalRef.current != null) {
        window.clearInterval(snapshotIntervalRef.current)
        snapshotIntervalRef.current = null
      }
      return
    }

    const pollSnapshot = async () => {
      try {
        const snapshot = await fetchMonitorSnapshot({
          symbol: backendSymbol || undefined,
          timeframe,
        })
        const payload = snapshot?.underlying ?? null
        const price = extractPrice(payload)
        if (price == null) return
        const timestamp = extractTimestamp(payload)
        updateRealtimeBar(price, timestamp)
      } catch (error) {
        console.error('[UnderlyingChart] Snapshot poll failed', error)
      }
    }

    pollSnapshot()
    snapshotIntervalRef.current = window.setInterval(() => {
      const lastStream = lastStreamUpdateRef.current
      const now = Date.now()
      if (!streamConnectedRef.current || now - lastStream > 2000) {
        pollSnapshot()
      }
    }, 1000)

    return () => {
      if (snapshotIntervalRef.current != null) {
        window.clearInterval(snapshotIntervalRef.current)
        snapshotIntervalRef.current = null
      }
    }
  }, [enableRealtime, backendSymbol, timeframe, extractPrice, extractTimestamp, updateRealtimeBar])

  useEffect(() => {
    return () => {
      const sessionId = sessionIdRef.current
      sessionIdRef.current = null
      if (sessionId) {
        deleteMonitorSession(sessionId).catch(() => undefined)
      }
      if (monitorWsRef.current) {
        monitorWsRef.current.close()
        monitorWsRef.current = null
      }
      if (snapshotIntervalRef.current != null) {
        window.clearInterval(snapshotIntervalRef.current)
        snapshotIntervalRef.current = null
      }
    }
  }, [])

  // Fetch labels on symbol/timeframe change
  useEffect(() => {
    const loadLabels = async () => {
      try {
        const result = await fetchLabels(symbol, timeframe);
        setLabels(Array.isArray(result?.labels) ? result.labels : []);
      } catch (error) {
        console.error('Failed to fetch labels:', error);
        setLabels([]); // Reset to empty array on error
      }
    };
    loadLabels();
  }, [symbol, timeframe]);

  // WebSocket connection for real-time label updates
  useEffect(() => {
    // Skip WebSocket in development until backend is properly configured
    if (process.env.NODE_ENV === 'development') {
      console.info('Skipping label WebSocket in development mode');
      return;
    }

    const connectWS = () => {
      try {
        const ws = connectLabelStream();
        wsRef.current = ws;

        ws.onopen = () => {
          console.log('Label WebSocket connected');
          subscribeLabelStream(ws, symbol, timeframe);
        };

        ws.onmessage = (event) => {
          const message = parseLabelMessage(event.data);
          if (!message) return;

          console.log('Label message received:', message);

          switch (message.type) {
            case 'label.create':
              // Refresh labels after create
              fetchLabels(symbol, timeframe).then(result => {
                setLabels(result.labels);
              }).catch(console.error);
              break;
            case 'label.update':
              // Handle label updates (Sprint 2)
              break;
            case 'label.delete':
              setLabels(prev => prev.filter(l => l.id !== message.payload.id));
              break;
          }
        };

        ws.onclose = () => {
          console.log('Label WebSocket disconnected');
        };

        ws.onerror = (error) => {
          console.error('Label WebSocket error:', error);
        };
      } catch (error) {
        console.error('Failed to connect label WebSocket:', error);
      }
    };

    connectWS();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [symbol, timeframe]);

  const handlePinPopup = useCallback((pinnedState: any) => {
    // Update the label with pinned cursor state
    console.log('Pinning popup with state:', pinnedState);
    // This will be implemented when we add the pinnedCursorState field to labels
  }, []);

  return (
    <div className="monitor-card">
      <div className="monitor-card__header">
        <div>
          <strong>{symbol}</strong>
          <span className="monitor-card__subtext"> Timeframe {timeframe}</span>
        </div>
        {loading && <span className="monitor-card__badge">Loading…</span>}
      </div>
      <div
        ref={containerRef}
        data-surface-id={surfaceId}
        style={{ width: '100%', height: CHART_HEIGHT }}
      />
      <ErrorBoundary fallback={<div style={{ padding: '10px', color: '#666' }}>Labels temporarily unavailable</div>}>
        <ChartLabels
          chart={chartRef.current}
          series={seriesRef.current}
          symbol={symbol}
          timeframe={timeframe}
          labels={Array.isArray(labels) ? labels : []}
          onLabelCreate={handleLabelCreate}
          onLabelUpdate={handleLabelUpdate}
          onLabelDelete={handleLabelDelete}
          onShowChart={handleShowChart}
          onContextAction={
            onContextAction
              ? (action: ChartContextMenuAction) =>
                  onContextAction({
                    ...action,
                    symbol,
                    timeframe,
                  })
              : undefined
          }
        />
      </ErrorBoundary>

      {/* Show Chart Popup */}
      {showChartPopup && (
        <ShowChartPopup
          underlying={showChartPopup.underlying}
          strike={showChartPopup.strike}
          timestamp={Number(showChartPopup.timestamp)}
          expiry={showChartPopup.expiry}
          onClose={() => setShowChartPopup(null)}
          onPin={handlePinPopup}
        />
      )}
    </div>
  )
}

export default UnderlyingChart
