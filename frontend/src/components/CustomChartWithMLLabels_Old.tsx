import React, { useEffect, useRef, useState } from 'react'
import {
  createChart,
  IChartApi,
  LineData,
  Time,
  SeriesMarker,
  CandlestickData,
  ISeriesApi,
  LogicalRangeChangeEventHandler,
} from 'lightweight-charts'
import { createPortal } from 'react-dom'

type ChartType = 'candle' | 'line'
type Timeframe = '1' | '5' | '15' | '30'

type Bar = {
  time: number // unix seconds
  open: number
  high: number
  low: number
  close: number
}

type CustomChartProps = {
  symbol?: string
  timeframe?: Timeframe
  chartType?: ChartType
  /** Explicit time range (otherwise lookbackSeconds is used) */
  fromSec?: number | null
  toSec?: number | null
  lookbackSeconds?: number
  height?: number
  historyUrlBuilder?: (symbol: string, fromSec: number, toSec: number, tf: Timeframe) => string
  marksUrlBuilder?: (symbol: string, tf: Timeframe, fromSec?: number, toSec?: number) => string
}

const DEFAULT_SYMBOL =
  (import.meta.env.VITE_CHART_SYMBOL as string | undefined) ??
  (import.meta.env.VITE_MONITOR_SYMBOL as string | undefined) ??
  'NIFTY50'
const DEFAULT_TF: Timeframe = '5'
const DEFAULT_TYPE: ChartType = 'candle'

const toSeconds = (ts: number | string | Date): number => {
  if (typeof ts === 'number') return ts > 2_000_000_000 ? Math.floor(ts / 1000) : ts
  return Math.floor(new Date(ts).getTime() / 1000)
}

const frameSeconds = (tf: Timeframe): number =>
  tf === '1' ? 60 : tf === '5' ? 300 : tf === '15' ? 900 : 1800

const LABEL_COLOR: Record<string, string> = {
  Bullish: '#00E676',  // bright green
  Bearish: '#FF1744',  // bright red
  Neutral: '#9CA3AF',  // grey
  Reversal: '#EAB308',
  Breakout: '#3B82F6',
}

function makeTickMarkFormatter() {
  const dFmt = new Intl.DateTimeFormat(undefined, { day: '2-digit', month: 'short' })
  const tFmt = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', hour12: false })
  let lastDayKey: string | null = null

  return (unixSec: number) => {
    const d = new Date(unixSec * 1000)
    const dayKey = `${d.getUTCFullYear()}-${d.getUTCMonth() + 1}-${d.getUTCDate()}`
    const timeTxt = tFmt.format(d)
    if (lastDayKey !== dayKey) {
      lastDayKey = dayKey
      return `${dFmt.format(d)}`
    }
    return timeTxt
  }
}

// ===== API helpers =====
type RawMark = { ts?: number | string; time?: number | string; label?: string; label_confidence?: number;[k: string]: any }

async function fetchBars(
  symbol: string,
  timeframe: Timeframe,
  fromSec: number,
  toSec: number,
  historyUrlBuilder?: CustomChartProps['historyUrlBuilder'],
): Promise<Bar[]> {
  const url =
    historyUrlBuilder?.(symbol, fromSec, toSec, timeframe) ??
    `/history?symbol=${encodeURIComponent(symbol)}&from=${fromSec}&to=${toSec}&resolution=${timeframe}`
  const res = await fetch(url, { cache: 'no-store' })
  if (!res.ok) return []
  let data: any
  try { data = await res.json() } catch { return [] }

  // 1) TV-shape
  if (data && data.s === 'ok' && Array.isArray(data.t)) {
    return data.t.map((t: number, i: number) => ({
      time: toSeconds(t),
      open: Number(data.o[i]),
      high: Number(data.h[i]),
      low: Number(data.l[i]),
      close: Number(data.c[i]),
    }))
  }
  // 2) array of objects
  if (Array.isArray(data)) {
    return data.map((row: any) => {
      const tRaw = row.time ?? row.ts ?? row.date
      const open = row.open ?? row.o
      const high = row.high ?? row.h
      const low = row.low ?? row.l
      const close = row.close ?? row.c
      if (tRaw == null || open == null) return null
      return { time: toSeconds(tRaw), open: +open, high: +high, low: +low, close: +close } as Bar
    }).filter((bar: Bar | null): bar is Bar => bar !== null)
  }
  // 3) wrapped
  if (data && Array.isArray(data.data)) {
    return data.data.map((row: any) => {
      const tRaw = row.time ?? row.ts ?? row.date
      if (tRaw == null) return null
      return { time: toSeconds(tRaw), open: +row.open, high: +row.high, low: +row.low, close: +row.close } as Bar
    }).filter((bar: Bar | null): bar is Bar => bar !== null)
  }
  return []
}

async function fetchMarksWithBackoff(
  symbol: string,
  timeframe: Timeframe,
  startFrom: number,
  startTo: number,
  marksUrlBuilder?: CustomChartProps['marksUrlBuilder'],
  maxMonthsBack: number = 18,
  stepDays: number = 30
): Promise<RawMark[]> {
  const build = (from: number, to: number) =>
    marksUrlBuilder
      ? marksUrlBuilder(symbol, timeframe, from, to)
      : `/marks?symbol=${encodeURIComponent(symbol)}&resolution=${timeframe}&from=${from}&to=${to}&include_neutral=true`

  const attempt = async (from: number, to: number) => {
    try {
      const res = await fetch(build(from, to), { cache: 'no-store' })
      const body = await res.text()
      if (!res.ok) return []
      let data: any
      try { data = JSON.parse(body) } catch { return [] }
      
      // Handle marks response format - extract marks array and convert to raw format
      let marks = []
      if (Array.isArray(data)) {
        marks = data
      } else if (data?.marks && Array.isArray(data.marks)) {
        marks = data.marks
      } else if (data?.data && Array.isArray(data.data)) {
        marks = data.data
      } else {
        return []
      }
      
      // Convert formatted marks to raw format
      return marks.map((r: any) => {
        let label = r.label ?? r.type ?? r.tag
        let confidence = r.label_confidence ?? r.confidence ?? r.score
        
        // If we got formatted text, parse it
        if (r.text && typeof r.text === 'string') {
          const textParts = r.text.split(' | ')
          if (textParts.length >= 1) {
            label = textParts[0] // "Bullish", "Bearish", "Neutral"
          }
          if (textParts.length >= 2 && textParts[1].startsWith('p=')) {
            confidence = parseFloat(textParts[1].substring(2)) // Keep as percentage
          }
        }
        
        return {
          ts: r.ts ?? r.time ?? r.t,
          time: r.ts ?? r.time ?? r.t,
          label: label,
          label_confidence: confidence,
          ...r,
        } as RawMark
      })
    } catch { return [] }
  }

  let rows = await attempt(startFrom, startTo)
  if (rows.length) return rows

  const maxSteps = Math.ceil(maxMonthsBack * (30 / stepDays))
  const step = stepDays * 24 * 3600
  let from = startFrom - step
  let to = startTo - step

  for (let i = 0; i < maxSteps; i++) {
    rows = await attempt(from, to)
    if (rows.length) return rows
    from -= step
    to -= step
    if (to <= 0) break
  }
  return []
}

async function fetchRawMarks(
  symbol: string,
  timeframe: Timeframe,
  _marksUrlBuilder?: CustomChartProps['marksUrlBuilder'],
  fromSec?: number,
  toSec?: number,
): Promise<RawMark[]> {
  const encSym = encodeURIComponent(symbol)
  const haveRange = typeof fromSec === 'number' && typeof toSec === 'number'

  const doFetch = async (url: string) => {
    try {
      const res = await fetch(url, { cache: 'no-store' })
      const body = await res.text()
      if (!res.ok || !body) return []
      let data: any
      try { data = JSON.parse(body) } catch { return [] }
      if (Array.isArray(data)) return data
      if (data?.marks && Array.isArray(data.marks)) return data.marks
      if (data?.data && Array.isArray(data.data)) return data.data
      return []
    } catch { return [] }
  }

  const canonical = haveRange
    ? `/marks?symbol=${encSym}&resolution=${timeframe}&from=${fromSec}&to=${toSec}&include_neutral=true`
    : `/marks?symbol=${encSym}&resolution=${timeframe}&include_neutral=true`

  const response = await doFetch(canonical)
  
  // Handle both raw array and wrapped response formats
  let rows = response
  if (response && response.marks && Array.isArray(response.marks)) {
    rows = response.marks
  }
  
  if (rows.length) {
    return rows.map((r: any) => {
      // Extract label from text field if it's formatted like "Bullish | p=69.94"
      let label = r.label ?? r.type ?? r.tag
      let confidence = r.label_confidence ?? r.confidence ?? r.score
      
      // If we got formatted text, parse it
      if (r.text && typeof r.text === 'string') {
        const textParts = r.text.split(' | ')
        if (textParts.length >= 1) {
          label = textParts[0] // "Bullish", "Bearish", "Neutral"
        }
        if (textParts.length >= 2 && textParts[1].startsWith('p=')) {
          confidence = parseFloat(textParts[1].substring(2)) // Keep as percentage
        }
      }
      
      return {
        ts: r.ts ?? r.time ?? r.t,
        time: r.ts ?? r.time ?? r.t,
        label: label,
        label_confidence: confidence,
        ...r,
      }
    })
  }

  return []
}

function mapMarksToSeriesMarkers(
  raw: RawMark[],
  bars: Bar[],
  tf: Timeframe,
): SeriesMarker<Time>[] {
  if (!bars.length) return []
  const tfSec = frameSeconds(tf)
  const times = bars.map(b => b.time) // already sorted by setData

  const nearestBarTime = (sec: number): number | null => {
    let lo = 0, hi = times.length - 1
    while (lo <= hi) {
      const mid = (lo + hi) >> 1
      if (times[mid] === sec) return times[mid]
      if (times[mid] < sec) lo = mid + 1
      else hi = mid - 1
    }
    const cand: number[] = []
    if (hi >= 0) cand.push(times[hi])
    if (lo < times.length) cand.push(times[lo])
    if (!cand.length) return null
    const best = cand.reduce((a, b) => Math.abs(b - sec) < Math.abs(a - sec) ? b : a, cand[0])
    const maxDelta = Math.floor(tfSec / 2)
    return Math.abs(best - sec) <= maxDelta ? best : null
  }

  const out: SeriesMarker<Time>[] = []
  console.log('DEBUG: Mapping', raw.length, 'raw marks to series markers')
  console.log('DEBUG: Available bar times range:', bars.length ? `${bars[0].time} to ${bars[bars.length-1].time}` : 'no bars')
  
  for (const r of raw) {
    const rawTs = r.ts ?? r.time
    if (rawTs == null) {
      console.log('DEBUG: Skipping mark with no timestamp:', r)
      continue
    }
    const sec = toSeconds(rawTs as any)
    const aligned = sec - (sec % tfSec)
    let t = nearestBarTime(aligned)
    if (t == null) t = nearestBarTime(sec)
    if (t == null) {
      console.log('DEBUG: No matching bar time for mark:', r, 'timestamp:', sec)
      continue
    }

    // Extract full label from text field or use the label field
    let txt = String(r.label ?? '')
    if ((r as any).text && typeof (r as any).text === 'string') {
      const textParts = (r as any).text.split(' | ')
      if (textParts.length >= 1) {
        txt = textParts[0] // "Bullish", "Bearish", "Neutral"
      }
    }
    
    const pos = /bull|buy|long/i.test(txt) ? 'belowBar' : 'aboveBar'
    const apiColor = (typeof (r as any).color === 'string' && /^#[0-9a-fA-F]{6}$/.test((r as any).color)) ? (r as any).color : undefined
    const lblKey = /bear|sell|short/i.test(txt) ? 'Bearish'
      : /bull|buy|long/i.test(txt) ? 'Bullish'
        : (txt || 'Neutral')
    const fallback = LABEL_COLOR[lblKey] ?? LABEL_COLOR['Neutral']
    const color = apiColor ?? fallback
    const rawMin = Number((r as any).minSize ?? 7)
    const size = Math.max(1, Math.min(3, Math.round(rawMin / 3)))

    const extra = r.label_confidence != null ? ` (${Math.round(Number(r.label_confidence))}%)` : ''
    const marker = {
      time: t as Time,
      position: pos as any,
      shape: 'circle' as const,
      color,
      text: (txt + extra).slice(0, 24),
      size,
    }
    // Only log the first few markers to avoid spam
    if (out.length < 3) {
      console.log('DEBUG: Creating marker sample:', marker, 'Raw label:', r.label, 'Text:', txt, 'Extra:', extra)
    }
    out.push(marker)
  }

  // de-dup by time+text+position+color
  console.log('DEBUG: Before deduplication:', out.length, 'markers')
  const seen = new Set<string>()
  const deduped = out.filter(m => {
    const k = `${m.time}|${m.text}|${m.position}|${(m as any).color ?? ''}`
    if (seen.has(k)) return false
    seen.add(k)
    return true
  })
  console.log('DEBUG: After deduplication:', deduped.length, 'markers')
  
  // Sort by time ascending (required by TradingView)
  const final = deduped.sort((a, b) => Number(a.time) - Number(b.time))
  console.log('DEBUG: After sorting:', final.length, 'markers')
  return final
}

function findBarByTimeFrom(bars: Bar[], ts: number): Bar | null {
  if (!bars.length) return null
  let lo = 0, hi = bars.length - 1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (bars[mid].time === ts) return bars[mid]
    if (bars[mid].time < ts) lo = mid + 1
    else hi = mid - 1
  }
  const i = Math.max(0, Math.min(bars.length - 1, lo))
  return bars[i] ?? null
}

// ===== Component =====
const CustomChartWithMLLabels: React.FC<CustomChartProps> = ({
  symbol = DEFAULT_SYMBOL,
  timeframe = DEFAULT_TF,
  chartType = DEFAULT_TYPE,
  fromSec = null,
  toSec = null,
  lookbackSeconds = 180 * 24 * 3600,
  height = 420,
  historyUrlBuilder,
  marksUrlBuilder,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const lineRef = useRef<ISeriesApi<'Line'> | null>(null)

  // keep latest bars for crosshair/menu
  const currentBarsRef = useRef<Record<Timeframe, Bar[]>>({
    '1': [], '5': [], '15': [], '30': []
  })
  const menuRef = useRef<HTMLDivElement | null>(null)

  // context menu + hover state
  const [menuOpen, setMenuOpen] = useState(false)
  const [menuXY, setMenuXY] = useState<{ x: number; y: number }>({ x: 0, y: 0 })
  const hoverRef = useRef<{ ts: number | null; price: number | null; bar: Bar | null }>({
    ts: null, price: null, bar: null,
  })
  const menuOpenRef = useRef(menuOpen)
  menuOpenRef.current = menuOpen
  
  // Store the hover data when menu opens to preserve it
  const menuDataRef = useRef<{ ts: number | null; price: number | null; bar: Bar | null }>({
    ts: null, price: null, bar: null,
  })

  // caches
  const dataCacheRef = useRef<Record<Timeframe, Bar[]>>({
    '1': [], '5': [], '15': [], '30': []
  })
  const markerCacheRef = useRef<Record<Timeframe, SeriesMarker<Time>[]>>({
    '1': [], '5': [], '15': [], '30': []
  })
  const earliestLoadedRef = useRef<Record<Timeframe, number | null>>({
    '1': null, '5': null, '15': null, '30': null
  })

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Create chart once
  useEffect(() => {
    if (!containerRef.current || chartRef.current) return
    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: { background: { color: '#0e1220' }, textColor: '#d1d4dc' },
      grid: { vertLines: { color: '#1e222d' }, horzLines: { color: '#1e222d' } },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
      handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: true },
      timeScale: {
        borderColor: '#2b3245',
        timeVisible: true,
        secondsVisible: false,
        tickMarkFormatter: makeTickMarkFormatter(),
        rightOffset: 4,
      },
      rightPriceScale: { borderColor: '#2b3245' },
      crosshair: { mode: 0 },
    })
    chartRef.current = chart

    candleRef.current = chart.addCandlestickSeries({
      upColor: '#26a69a', downColor: '#ef5350',
      borderUpColor: '#26a69a', borderDownColor: '#ef5350',
      wickUpColor: '#26a69a', wickDownColor: '#ef5350',
    })
    lineRef.current = chart.addLineSeries({ priceLineVisible: false, color: '#4da3ff' })
    lineRef.current.applyOptions({ visible: false })

    const onResize = () => {
      if (!containerRef.current || !chartRef.current) return
      chartRef.current.applyOptions({ width: containerRef.current.clientWidth, height })
    }
    window.addEventListener('resize', onResize)

    const onCrosshair = (param: any) => {
      if (!param?.time) {
        hoverRef.current = { ts: null, price: null, bar: null }
        return
      }
      const ts = typeof param.time === 'number' ? param.time : (param.time as any)
      let price: number | null = null
      if (param.seriesPrices) {
        const series = (chartType === 'candle' ? candleRef.current : lineRef.current) ?? candleRef.current
        const p = param.seriesPrices.get((series as unknown) as any)
        price = typeof p === 'number' ? p : (p?.close ?? null)
      }
      const bars = currentBarsRef.current[timeframe] ?? []
      const bar = findBarByTimeFrom(bars, ts)
      hoverRef.current = { ts, price, bar }
    }
    chart.subscribeCrosshairMove(onCrosshair)

    const el = containerRef.current!
    console.log('[DEBUG] Setting up context menu on element:', el)
    
    const onContext = (e: MouseEvent) => {
      console.log('[DEBUG] Context menu triggered!', e)
      e.preventDefault()
      // Capture the current hover data when menu opens
      menuDataRef.current = { ...hoverRef.current }
      console.log('[menu] open @', e.clientX, e.clientY, 'hover=', hoverRef.current)
      setMenuXY({ x: e.clientX, y: e.clientY })
      setMenuOpen(true)
    }
    el.addEventListener('contextmenu', onContext)
    
    // Add a test listener to see if ANY mouse events work
    const onTestClick = (e: MouseEvent) => {
      console.log('[DEBUG] ANY click detected:', e.type, e.button)
    }
    el.addEventListener('mousedown', onTestClick)
    el.addEventListener('mouseup', onTestClick)
    el.addEventListener('click', onTestClick)
    
    console.log('[DEBUG] Context menu listener added')

    const onDocPointerDown = (ev: PointerEvent) => {
      if (!menuOpenRef.current) return
      const target = ev.target as Node | null
      if (menuRef.current && target && menuRef.current.contains(target)) {
        return // clicks inside the menu shouldn't close it
      }
      setMenuOpen(false)
    }
    document.addEventListener('pointerdown', onDocPointerDown)

    return () => {
      document.removeEventListener('pointerdown', onDocPointerDown)
      window.removeEventListener('resize', onResize)
      chart.unsubscribeCrosshairMove(onCrosshair)
      el.removeEventListener('contextmenu', onContext)
      // Clean up test listeners
      el.removeEventListener('mousedown', onTestClick)
      el.removeEventListener('mouseup', onTestClick)
      el.removeEventListener('click', onTestClick)
    }
  }, [height, chartType, timeframe])

  // Toggle chart type
  useEffect(() => {
    if (!candleRef.current || !lineRef.current) return
    const showCandle = chartType === 'candle'
    candleRef.current.applyOptions({ visible: showCandle })
    lineRef.current.applyOptions({ visible: !showCandle })

    const mk = markerCacheRef.current[timeframe] ?? []
    candleRef.current.setMarkers(mk)
    lineRef.current.setMarkers(mk)
  }, [chartType, timeframe])

  // Load initial data
  useEffect(() => {
    let cancelled = false
    const run = async () => {
      if (!chartRef.current || !candleRef.current || !lineRef.current) return
      setLoading(true); setError(null)

      try {
        // Use more recent time range where all timeframes have data
        const to = toSec ?? 1729720000 // More recent data
        const from = fromSec ?? 1729680000 // Recent data range with all timeframes

        // Clear cache to ensure we get fresh data with user-only labels
        dataCacheRef.current[timeframe] = []
        markerCacheRef.current[timeframe] = []
        earliestLoadedRef.current[timeframe] = null

        let bars = await fetchBars(symbol, timeframe, from, to, historyUrlBuilder)
        if (cancelled) return
        dataCacheRef.current[timeframe] = bars
        currentBarsRef.current[timeframe] = bars
        earliestLoadedRef.current[timeframe] = bars.length ? bars[0].time : from

        candleRef.current.setData(bars as unknown as CandlestickData[])
        lineRef.current.setData(bars.map(b => ({ time: b.time as Time, value: b.close })) as LineData[])

        const rawMarks = await fetchMarksWithBackoff(symbol, timeframe, from, to, marksUrlBuilder)
        const markers = mapMarksToSeriesMarkers(rawMarks, bars, timeframe)
        if (cancelled) return
        markerCacheRef.current[timeframe] = markers
        candleRef.current.setMarkers(markers)
        lineRef.current.setMarkers(markers)

        chartRef.current.timeScale().fitContent()
      } catch (e: any) {
        if (!cancelled) setError(e?.message ?? 'Failed to load chart data')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    run()
    return () => { cancelled = true }
  }, [symbol, timeframe, fromSec, toSec, lookbackSeconds, historyUrlBuilder, marksUrlBuilder])

  // Infinite scroll left
  useEffect(() => {
    if (!chartRef.current || !candleRef.current) return

    const handler: LogicalRangeChangeEventHandler = async (range) => {
      if (!range) return
      const bars = dataCacheRef.current[timeframe] ?? []
      if (!bars.length) return

      const logicalFrom = range.from
      const threshold = 10
      if (logicalFrom <= threshold) {
        const earliest = earliestLoadedRef.current[timeframe] ?? bars[0].time
        const chunk = 120 * frameSeconds(timeframe)
        // Limit how far back we can go - don't go before our recent data range
        const minTime = 1729680000 // Same as our recent data range
        const newFrom = Math.max(earliest - chunk, minTime)
        const newTo = earliest - 1
        if (newTo <= newFrom || newFrom < minTime) return

        const older = await fetchBars(symbol, timeframe, newFrom, newTo, historyUrlBuilder)
        if (!older.length) return

        const merged = [...older.filter(b => b.time < bars[0].time), ...bars]
        dataCacheRef.current[timeframe] = merged
        currentBarsRef.current[timeframe] = merged
        earliestLoadedRef.current[timeframe] = merged[0].time

        candleRef.current!.setData(merged as unknown as CandlestickData[])
        lineRef.current!.setData(merged.map(b => ({ time: b.time as Time, value: b.close })) as LineData[])

        const rawOlderMarks = await fetchRawMarks(symbol, timeframe, marksUrlBuilder, newFrom, newTo)
        const olderMarkers = mapMarksToSeriesMarkers(rawOlderMarks, older, timeframe)
        if (olderMarkers.length) {
          const all = (markerCacheRef.current[timeframe] ?? []).concat(olderMarkers)
          const seen = new Set<string>()
          const dedup = all.filter(m => {
            const key = `${m.time}|${m.text}|${m.position}|${(m as any).color ?? ''}`
            if (seen.has(key)) return false
            seen.add(key); return true
          })
          markerCacheRef.current[timeframe] = dedup
          candleRef.current!.setMarkers(dedup)
          lineRef.current!.setMarkers(dedup)
        }
      }
    }

    const ts = chartRef.current.timeScale()
    ts.subscribeVisibleLogicalRangeChange(handler)
    return () => { ts.unsubscribeVisibleLogicalRangeChange(handler) }
  }, [symbol, timeframe, historyUrlBuilder, marksUrlBuilder])

  // === marker refresh helper ===
  const refreshMarkers = async () => {
    if (!candleRef.current || !lineRef.current) return
    
    const bars = dataCacheRef.current[timeframe] || []
    if (!bars.length) return
    
    try {
      const from = bars[0].time
      const to = bars[bars.length - 1].time
      console.log(`Refreshing markers for ${symbol} ${timeframe} from ${from} to ${to}`)
      
      const rawMarks = await fetchRawMarks(symbol, timeframe, marksUrlBuilder, from, to)
      console.log('Fetched fresh marks:', rawMarks.length)
      
      // Debug: Log first few raw marks to see structure
      console.log('DEBUG: Sample raw marks:', JSON.stringify(rawMarks.slice(0, 3), null, 2))
      
      // All labels are now user-created (backend filters to 100% confidence only)
      console.log('DEBUG: User-created labels found:', rawMarks.length)
      if (rawMarks.length > 0) {
        console.log('DEBUG: Sample user labels:', rawMarks.slice(0, 3))
      }
      
      const markers = mapMarksToSeriesMarkers(rawMarks, bars, timeframe)
      markerCacheRef.current[timeframe] = markers
      
      // All markers are now user-created
      console.log('DEBUG: User markers mapped:', markers.length, markers.slice(0, 2))
      
      candleRef.current.setMarkers(markers)
      lineRef.current.setMarkers(markers)
      
      console.log(`Updated chart with ${markers.length} markers`)
    } catch (error) {
      console.error('Failed to refresh markers:', error)
    }
  }

  // === label actions ===
  const saveLabel = async (label: string) => {
    console.log('[menu] saveLabel', label, menuDataRef.current)
    setMenuOpen(false)
    
    if (!menuDataRef.current.ts) {
      console.error('No timestamp available for label')
      return
    }
    
    // Debug: Log the exact timestamp being saved
    const saveTimestamp = menuDataRef.current.ts
    const saveDate = new Date(saveTimestamp * 1000)
    console.log('DEBUG: Saving label at timestamp:', saveTimestamp, 'Date:', saveDate.toISOString())
    
    try {
      const response = await fetch('/api/labels', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol,
          timeframe,
          timestamp: menuDataRef.current.ts,
          label,
          price: menuDataRef.current.price || menuDataRef.current.bar?.close,
          ohlc: menuDataRef.current.bar
        })
      })
      
      if (response.ok) {
        const result = await response.json()
        console.log('Label saved successfully:', result)
        
        // Refresh markers from backend
        await refreshMarkers()
      } else {
        const errorText = await response.text()
        console.error('Failed to save label:', errorText)
      }
    } catch (error) {
      console.error('Error saving label:', error)
    }
  }
  
  const deleteLabel = async () => {
    console.log('[menu] deleteLabel', menuDataRef.current)
    setMenuOpen(false)
    
    if (!menuDataRef.current.ts) {
      console.error('No timestamp available for label deletion')
      return
    }
    
    // Debug: Log deletion details (all labels are now user-created)
    console.log('DEBUG: Deleting user label at timestamp:', menuDataRef.current.ts)
    
    try {
      const response = await fetch('/api/labels', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol,
          timeframe,
          timestamp: menuDataRef.current.ts
        })
      })
      
      if (response.ok) {
        const result = await response.json()
        console.log('Label deleted successfully:', result)
        
        // Refresh markers from backend
        await refreshMarkers()
      } else {
        const errorText = await response.text()
        console.error('Failed to delete label:', errorText)
      }
    } catch (error) {
      console.error('Error deleting label:', error)
    }
  }

  return (
    <div 
      style={{ display: 'flex', flexDirection: 'column' }}
      onContextMenu={(_e) => {
        console.log('[DEBUG] Parent div context menu triggered!')
        // Don't prevent default here - let it bubble to chart
      }}
    >
      <div 
        ref={containerRef} 
        style={{ width: '100%', height }}
        onContextMenu={(_e) => {
          console.log('[DEBUG] Chart container context menu triggered!')
          // Don't prevent default here either
        }}
      />

      {/* footer / debug */}
      <div
        style={{
          padding: '8px 12px',
          borderTop: '1px solid #1e222d',
          fontSize: 12,
          color: '#9aa4bf',
          display: 'flex',
          gap: 16,
          flexWrap: 'wrap',
        }}
      >
        <span>
          Markers: 1m:{markerCacheRef.current['1']?.length ?? 0} | 5m:{markerCacheRef.current['5']?.length ?? 0} | 15m:{markerCacheRef.current['15']?.length ?? 0} | 30m:{markerCacheRef.current['30']?.length ?? 0}
        </span>
        <span style={{ marginLeft: 'auto' }}>{loading ? 'Loading…' : error ? `Error: ${error}` : null}</span>
      </div>

      {/* context menu (portal) */}
      {menuOpen && createPortal(
        <div
          ref={menuRef}
          style={{
            position: 'fixed',
            left: menuXY.x,
            top: menuXY.y,
            background: '#111826',
            color: '#d1d4dc',
            border: '1px solid #1f2937',
            borderRadius: 8,
            boxShadow: '0 8px 24px rgba(0,0,0,.4)',
            zIndex: 2147483647,
            padding: 6,
            minWidth: 160,
            fontSize: 12,
            pointerEvents: 'auto',
            userSelect: 'none',
          }}
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => e.stopPropagation()}
          onContextMenu={(e) => { e.preventDefault(); e.stopPropagation() }}
        >
          <div
            style={{ padding: '8px 10px', cursor: 'pointer' }}
            onMouseDown={(e) => { e.preventDefault(); e.stopPropagation() }}
            onClick={() => { console.log('[menu] click Bullish'); saveLabel('Bullish') }}
          >
            ➕ Set Bullish
          </div>
          <div
            style={{ padding: '8px 10px', cursor: 'pointer' }}
            onMouseDown={(e) => { e.preventDefault(); e.stopPropagation() }}
            onClick={() => { console.log('[menu] click Bearish'); saveLabel('Bearish') }}
          >
            ➕ Set Bearish
          </div>
          <div
            style={{ padding: '8px 10px', cursor: 'pointer' }}
            onMouseDown={(e) => { e.preventDefault(); e.stopPropagation() }}
            onClick={() => { console.log('[menu] click Neutral'); saveLabel('Neutral') }}
          >
            ➕ Set Neutral
          </div>
          <hr style={{ borderColor: '#1f2937', margin: '6px 0' }} />
          <div
            style={{ padding: '8px 10px', cursor: 'pointer', color: '#ef4444' }}
            onMouseDown={(e) => { e.preventDefault(); e.stopPropagation() }}
            onClick={() => { console.log('[menu] click delete'); deleteLabel() }}
          >
            🗑️ Clear label
          </div>
        </div>,
        document.body
      )}
    </div>
  )
}

export default CustomChartWithMLLabels
