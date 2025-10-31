import { useEffect, useRef, useState, useCallback } from 'react'
import { createChart, type IChartApi, type ISeriesApi, type CandlestickData, type Time, type MouseEventParams, type Range, type BusinessDay } from 'lightweight-charts'
import { useMonitorSync } from './MonitorSyncContext'
import { ChartLabels } from '../chart-labels/ChartLabels'
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

type Timeframe = '1' | '2' | '3' | '5' | '15' | '30' | '60' | '1D'

export interface UnderlyingChartProps {
  symbol: string
  timeframe: Timeframe
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

const UnderlyingChart = ({ symbol, timeframe }: UnderlyingChartProps) => {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const [loading, setLoading] = useState(false)
  const [labels, setLabels] = useState<Label[]>([])
  const [showChartPopup, setShowChartPopup] = useState<{
    underlying: string
    strike: number
    timestamp: string
    expiry: string
  } | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const { setTimeRange, setCrosshairTime, setPriceRange } = useMonitorSync()

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

    const resize = () => {
      chart.applyOptions({ width: containerRef.current?.clientWidth ?? 800 })
    }
    window.addEventListener('resize', resize)

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
      window.removeEventListener('resize', resize)
      chart.timeScale().unsubscribeVisibleTimeRangeChange(handleTimeRange)
      chart.unsubscribeCrosshairMove(handleCrosshair)
      container?.removeEventListener('wheel', handleWheel)
      container?.removeEventListener('mouseup', handleMouseUp)
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
    }
  }, [symbol, timeframe, setTimeRange, setCrosshairTime, syncPriceRange])

  useEffect(() => {
    const load = async () => {
      if (!seriesRef.current) return
      setLoading(true)
      const bars = await fetchBars(symbol, timeframe)
      seriesRef.current.setData(bars.map(toCandle))
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
      <div ref={containerRef} style={{ width: '100%', height: CHART_HEIGHT }} />
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
