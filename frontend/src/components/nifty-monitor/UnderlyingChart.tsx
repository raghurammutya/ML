import { useEffect, useRef, useState, useCallback } from 'react'
import { createChart, type IChartApi, type ISeriesApi, type CandlestickData, type Time, type MouseEventParams, type Range, type BusinessDay } from 'lightweight-charts'
import { useMonitorSync } from './MonitorSyncContext'

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
    </div>
  )
}

export default UnderlyingChart
