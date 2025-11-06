import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
  type CandlestickData,
} from 'lightweight-charts'
import { useMonitorSync } from '../nifty-monitor/MonitorSyncContext'
import { connectFoStream, normalizeFoSymbol } from '../../services/fo'
import { fetchMonitorMetadata } from '../../services/monitor'
import type { MonitorOptionLeg, MonitorOptionStrike } from '../../types'
import type { UnderlyingChartProps } from '../nifty-monitor/UnderlyingChart'
import { normalizeUnderlyingSymbol } from '../../utils/symbols'
import styles from '../../pages/TradingDashboard.module.css'

interface OptionChartProps {
  underlying: string
  expiry: string
  strike: number
  timeframe: UnderlyingChartProps['timeframe']
  side: 'call' | 'put' | 'straddle'
  title?: string
}

interface PopupUpdateMessage {
  type: string
  timestamp: string | number
  option_side?: 'call' | 'put'
  candle?: {
    o: number
    h: number
    l: number
    c: number
    v?: number
  }
  metrics?: {
    premium?: number
    iv?: number
    delta?: number
    gamma?: number
    theta?: number
    vega?: number
    oi?: number
    oi_delta?: number
  }
}

const mapTimeframeToFo = (timeframe: UnderlyingChartProps['timeframe']): string => {
  switch (timeframe) {
    case '1':
      return '1m'
    case '2':
      return '2m'
    case '3':
      return '3m'
    case '5':
      return '5m'
    case '15':
      return '15m'
    case '30':
      return '30m'
    case '60':
      return '60m'
    case '1D':
      return '1d'
    default:
      return '5m'
  }
}

const timeframeToSeconds = (timeframe: UnderlyingChartProps['timeframe']): number => {
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

const normalizeBucketTime = (timestampSeconds: number, timeframe: UnderlyingChartProps['timeframe']): number => {
  if (timeframe === '1D') {
    const date = new Date(timestampSeconds * 1000)
    date.setUTCHours(0, 0, 0, 0)
    return Math.floor(date.getTime() / 1000)
  }
  const interval = timeframeToSeconds(timeframe)
  return timestampSeconds - (timestampSeconds % interval)
}

const OptionChart: React.FC<OptionChartProps> = ({ underlying, expiry, strike, timeframe, side, title }) => {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const lastBarRef = useRef<CandlestickData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [legs, setLegs] = useState<{ call: MonitorOptionLeg | null; put: MonitorOptionLeg | null }>({
    call: null,
    put: null,
  })
  const [latestPrice, setLatestPrice] = useState<number | null>(null)
  const [latestMetrics, setLatestMetrics] = useState<{
    iv: number | null
    delta: number | null
    gamma: number | null
    theta: number | null
    vega: number | null
    oi: number | null
    oi_delta: number | null
  }>({
    iv: null,
    delta: null,
    gamma: null,
    theta: null,
    vega: null,
    oi: null,
    oi_delta: null,
  })
  const latestPremiumsRef = useRef<{ call?: number; put?: number }>({})

  const { setCrosshairTime, setCrosshairPrice, setCrosshairRatio, setTimeRange, setPriceRange } = useMonitorSync()

  const computeAggregatedPremium = useCallback(
    (premiums: { call?: number; put?: number }): number | null => {
      if (side === 'call') {
        return premiums.call ?? null
      }
      if (side === 'put') {
        return premiums.put ?? null
      }
      const callPremium = premiums.call
      const putPremium = premiums.put
      if (callPremium == null || putPremium == null) {
        return null
      }
      return callPremium + putPremium
    },
    [side],
  )

  const seedInitialBar = useCallback(
    (price: number) => {
      if (!chartRef.current || !seriesRef.current) return
      const nowSeconds = Math.floor(Date.now() / 1000)
      const initial: CandlestickData = {
        time: normalizeBucketTime(nowSeconds, timeframe) as Time,
        open: price,
        high: price,
        low: price,
        close: price,
      }
      seriesRef.current.setData([initial])
      lastBarRef.current = initial
      setTimeRange({ from: initial.time as number, to: initial.time as number })
      setPriceRange({ min: price, max: price })
    },
    [setPriceRange, setTimeRange, timeframe],
  )

  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 320,
      layout: { background: { color: 'rgba(15, 23, 42, 0.78)' }, textColor: '#e2e8f0' },
      grid: {
        vertLines: { color: 'rgba(148, 163, 184, 0.12)' },
        horzLines: { color: 'rgba(148, 163, 184, 0.12)' },
      },
      timeScale: {
        borderColor: 'rgba(148, 163, 184, 0.2)',
        timeVisible: timeframe !== '1D',
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: 'rgba(148, 163, 184, 0.2)',
      },
    })

    const series = chart.addCandlestickSeries({
      upColor: '#34d399',
      downColor: '#f87171',
      borderUpColor: '#34d399',
      borderDownColor: '#f87171',
      wickUpColor: '#34d399',
      wickDownColor: '#f87171',
    })

    chartRef.current = chart
    seriesRef.current = series

    const handleResize = () => {
      if (!containerRef.current || !chart) return
      chart.applyOptions({ width: containerRef.current.clientWidth })
    }

    const handleCrosshair = (params: any) => {
      if (!params || params.time === undefined) {
        setCrosshairTime(null)
        setCrosshairPrice(null)
        setCrosshairRatio(null)
        return
      }
      const time = typeof params.time === 'number' ? params.time : (params.time as Time as number)
      setCrosshairTime(time)
      if (params.seriesPrices?.get(series)) {
        const price = params.seriesPrices.get(series)
        if (typeof price === 'number') {
          setCrosshairPrice(price)
        }
      }
      if (chartRef.current) {
        const width = chartRef.current.timeScale().width()
        const coordinate = chartRef.current.timeScale().timeToCoordinate(params.time as Time)
        if (coordinate != null && width) {
          setCrosshairRatio(coordinate / width)
        }
      }
    }

    window.addEventListener('resize', handleResize)
    chart.subscribeCrosshairMove(handleCrosshair)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.unsubscribeCrosshairMove(handleCrosshair)
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
    }
  }, [setCrosshairPrice, setCrosshairRatio, setCrosshairTime, timeframe])

  const resolveInstrument = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const normalized = normalizeUnderlyingSymbol(underlying)
      const response = await fetchMonitorMetadata({ symbol: normalized, otm_levels: 50 })
      const optionExpiries = response.options || []
      const matchedExpiry = optionExpiries.find((entry) => entry.expiry === expiry)
      if (!matchedExpiry) {
        throw new Error(`Unable to find expiry ${expiry}`)
      }

      const strikes = matchedExpiry.strikes || []
      const matchedStrike = strikes.find((entry: MonitorOptionStrike) => Math.abs(entry.strike - strike) < 0.1)
      if (!matchedStrike) {
        throw new Error(`Unable to find strike ${strike}`)
      }

      const callLeg = matchedStrike.call ?? null
      const putLeg = matchedStrike.put ?? null

      if (side === 'call' && !callLeg) {
        throw new Error('Call leg not available for this strike')
      }
      if (side === 'put' && !putLeg) {
        throw new Error('Put leg not available for this strike')
      }
      if (side === 'straddle' && (!callLeg || !putLeg)) {
        throw new Error('Both call and put legs are required for a straddle view')
      }

      setLegs({ call: callLeg, put: putLeg })

      const nextPremiums: { call?: number; put?: number } = {}
      if (callLeg?.last_price != null && Number.isFinite(Number(callLeg.last_price))) {
        nextPremiums.call = Number(callLeg.last_price)
      }
      if (putLeg?.last_price != null && Number.isFinite(Number(putLeg.last_price))) {
        nextPremiums.put = Number(putLeg.last_price)
      }
      latestPremiumsRef.current = nextPremiums

      const aggregated = computeAggregatedPremium(nextPremiums)
      if (aggregated != null) {
        setLatestPrice(aggregated)
        seedInitialBar(aggregated)
      } else {
        lastBarRef.current = null
        seriesRef.current?.setData([])
        setLatestPrice(null)
      }
    } catch (err) {
      console.error('[OptionChart] Failed to resolve instrument', err)
      setError(err instanceof Error ? err.message : 'Failed to resolve option instrument')
    } finally {
      setLoading(false)
    }
  }, [computeAggregatedPremium, expiry, seedInitialBar, side, strike, underlying])

  useEffect(() => {
    resolveInstrument()
    return () => {
      setLegs({ call: null, put: null })
      latestPremiumsRef.current = {}
      setLatestMetrics({
        iv: null,
        delta: null,
        gamma: null,
        theta: null,
        vega: null,
        oi: null,
        oi_delta: null,
      })
      lastBarRef.current = null
    }
  }, [resolveInstrument])

  const updateRealtimeBar = useCallback(
    (price: number, timestampSeconds: number) => {
      if (!seriesRef.current || !chartRef.current) return
      if (!Number.isFinite(price)) return
      const bucketTime = normalizeBucketTime(timestampSeconds, timeframe)
      const interval = timeframeToSeconds(timeframe)
      const lastBar = lastBarRef.current

      if (lastBar && typeof lastBar.time === 'number' && lastBar.time === bucketTime) {
        const updated: CandlestickData = {
          ...lastBar,
          close: price,
          high: Math.max(lastBar.high, price),
          low: Math.min(lastBar.low, price),
        }
        lastBarRef.current = updated
        seriesRef.current.update(updated)
      } else {
        const previousClose = lastBar?.close ?? price
        const newBar: CandlestickData = {
          time: bucketTime as Time,
          open:
            lastBar && typeof lastBar.time === 'number' && bucketTime - lastBar.time <= interval
              ? lastBar.close
              : price,
          high: Math.max(previousClose, price),
          low: Math.min(previousClose, price),
          close: price,
        }
        lastBarRef.current = newBar
        seriesRef.current.update(newBar)
      }

      const minPrice = Math.min(lastBarRef.current?.low ?? price, price)
      const maxPrice = Math.max(lastBarRef.current?.high ?? price, price)
      setPriceRange({ min: minPrice, max: maxPrice })

      const visibleRange = chartRef.current.timeScale().getVisibleRange()
      if (visibleRange && visibleRange.from != null && visibleRange.to != null) {
        const fromValue = typeof visibleRange.from === 'number' ? visibleRange.from : (visibleRange.from as Time as number)
        const toValue = typeof visibleRange.to === 'number' ? visibleRange.to : (visibleRange.to as Time as number)
        setTimeRange({ from: fromValue, to: toValue })
      }
    },
    [setPriceRange, setTimeRange, timeframe]
  )

  const hasRequiredLegs = useMemo(() => {
    if (side === 'call') return Boolean(legs.call)
    if (side === 'put') return Boolean(legs.put)
    return Boolean(legs.call && legs.put)
  }, [legs, side])

  useEffect(() => {
    if (!hasRequiredLegs) return
    const foTimeframe = mapTimeframeToFo(timeframe)
    const ws = connectFoStream()
    wsRef.current = ws

    ws.onopen = () => {
      const sidesToSubscribe: ('call' | 'put')[] =
        side === 'straddle' ? ['call', 'put'] : [side]
      sidesToSubscribe.forEach((legSide) => {
        const payload = {
          action: 'subscribe_popup',
          underlying: normalizeFoSymbol(underlying),
          strike,
          expiry,
          timeframe: foTimeframe,
          option_side: legSide,
        }
        ws.send(JSON.stringify(payload))
      })
    }

    ws.onmessage = (event) => {
      try {
        if (typeof event.data !== 'string' || !event.data.startsWith('{')) {
          return
        }
        const data: PopupUpdateMessage = JSON.parse(event.data)
        if (data.type === 'popup_update') {
          const payloadSide: 'call' | 'put' = data.option_side === 'put' ? 'put' : 'call'
          if (side === 'call' && payloadSide !== 'call') return
          if (side === 'put' && payloadSide !== 'put') return
          const ts = typeof data.timestamp === 'number'
            ? data.timestamp
            : Math.floor(new Date(data.timestamp).getTime() / 1000)
          const price = data.metrics?.premium ?? data.candle?.c
          if (typeof price === 'number' && price > 0) {
            latestPremiumsRef.current[payloadSide] = price
            const aggregated = computeAggregatedPremium(latestPremiumsRef.current)
            if (aggregated != null) {
              setLatestPrice(aggregated)
              updateRealtimeBar(aggregated, ts)
            }
          }
          if (data.metrics) {
            setLatestMetrics((prev) => ({
              iv: typeof data.metrics?.iv === 'number' ? data.metrics.iv : prev.iv,
              delta: typeof data.metrics?.delta === 'number' ? data.metrics.delta : prev.delta,
              gamma: typeof data.metrics?.gamma === 'number' ? data.metrics.gamma : prev.gamma,
              theta: typeof data.metrics?.theta === 'number' ? data.metrics.theta : prev.theta,
              vega: typeof data.metrics?.vega === 'number' ? data.metrics.vega : prev.vega,
              oi: typeof data.metrics?.oi === 'number' ? data.metrics.oi : prev.oi,
              oi_delta: typeof data.metrics?.oi_delta === 'number' ? data.metrics.oi_delta : prev.oi_delta,
            }))
          }
        }
      } catch (err) {
        console.error('[OptionChart] Failed to process popup update', err)
      }
    }

    ws.onerror = (event) => {
      console.error('[OptionChart] WebSocket error', event)
    }

    return () => {
      ws.close()
      wsRef.current = null
    }
  }, [computeAggregatedPremium, expiry, hasRequiredLegs, side, strike, timeframe, underlying, updateRealtimeBar])

  const sideLabel = side === 'straddle' ? 'Straddle' : side.toUpperCase()

  const heading = useMemo(() => {
    if (title) return title
    if (side === 'call') {
      return legs.call?.tradingsymbol ?? `${normalizeUnderlyingSymbol(underlying)} ${strike.toFixed(0)} CALL`
    }
    if (side === 'put') {
      return legs.put?.tradingsymbol ?? `${normalizeUnderlyingSymbol(underlying)} ${strike.toFixed(0)} PUT`
    }
    const base = `${normalizeUnderlyingSymbol(underlying)} ${strike.toFixed(0)}`
    return `${base} Straddle`
  }, [legs.call, legs.put, side, strike, title, underlying])

  const metricsDisplay = useMemo(() => {
    const format = (value: number | null, decimals = 2) => {
      if (value == null || !Number.isFinite(value)) return '—'
      return value.toFixed(decimals)
    }
    return [
      { label: 'IV', value: format(latestMetrics.iv, 3) },
      { label: 'Δ', value: format(latestMetrics.delta, 4) },
      { label: 'Γ', value: format(latestMetrics.gamma, 5) },
      { label: 'Θ', value: format(latestMetrics.theta, 2) },
      { label: 'Vega', value: format(latestMetrics.vega, 2) },
      {
        label: 'OI',
        value:
          latestMetrics.oi != null && Number.isFinite(latestMetrics.oi)
            ? Math.round(latestMetrics.oi).toLocaleString('en-IN')
            : '—',
      },
      {
        label: 'OI Δ',
        value:
          latestMetrics.oi_delta != null && Number.isFinite(latestMetrics.oi_delta)
            ? Math.round(latestMetrics.oi_delta).toLocaleString('en-IN')
            : '—',
      },
    ]
  }, [latestMetrics])

  return (
    <div className={styles.optionChartCard}>
      <div className={styles.optionChartHeader}>
        <div>
          <div className={styles.optionChartTitle}>{heading}</div>
          <div className={styles.optionChartSubtitle}>
            Expiry {expiry} • Strike {strike.toLocaleString('en-IN')} • {sideLabel}
          </div>
        </div>
        <div className={styles.optionChartPrice}>
          {latestPrice != null ? latestPrice.toFixed(2) : '—'}
        </div>
      </div>
      <div className={styles.optionChartMetrics}>
        {metricsDisplay.map((metric) => (
          <div key={metric.label} className={styles.optionChartMetric}>
            <span className={styles.optionChartMetricLabel}>{metric.label}</span>
            <span className={styles.optionChartMetricValue}>{metric.value}</span>
          </div>
        ))}
      </div>
      <div className={styles.optionChartBody} ref={containerRef} />
      {loading && <div className={styles.optionChartFooter}>Resolving option instrument…</div>}
      {error && <div className={`${styles.optionChartFooter} ${styles.optionChartError}`}>{error}</div>}
    </div>
  )
}

export default OptionChart
