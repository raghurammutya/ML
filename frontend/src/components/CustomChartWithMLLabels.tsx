import React, { useEffect, useRef, useState } from 'react'
import {
  createChart,
  IChartApi,
  LineData,
  Time,
  SeriesMarker,
  CandlestickData,
  ISeriesApi,
} from 'lightweight-charts'
import { createPortal } from 'react-dom'

type ChartType = 'candle' | 'line'
type Timeframe = '1' | '2' | '3' | '5' | '15' | '30' | '60' | '1D'

type Bar = {
  time: number
  open: number
  high: number
  low: number
  close: number
}

type CustomChartProps = {
  symbol?: string
  timeframe?: Timeframe
  chartType?: ChartType
  height?: number
  fromSec?: number | null
  toSec?: number | null
}

const DEFAULT_SYMBOL = 'NIFTY50'
const DEFAULT_TF: Timeframe = '5'  // Testing 5-minute data
const DEFAULT_TYPE: ChartType = 'candle'

// Time ranges for different timeframes - now supports infinite scrolling
const getInitialTimeRange = (timeframe: Timeframe): { from: number; to: number } => {
  // Use dynamic timestamps based on current time
  const now = Math.floor(Date.now() / 1000)  // Current time in seconds
  
  switch (timeframe) {
    case '1D':
      // For daily data, show last 6 months
      return { 
        from: now - (6 * 30 * 24 * 3600),  // 6 months ago
        to: now
      }
    case '60':
      // For hourly data, show last 30 days
      return {
        from: now - (30 * 24 * 3600),      // 30 days ago
        to: now
      }
    case '30':
      // For 30min data, show last 21 days
      return {
        from: now - (21 * 24 * 3600),      // 21 days ago
        to: now
      }
    case '15':
      // For 15min data, show last 14 days
      return {
        from: now - (14 * 24 * 3600),      // 14 days ago
        to: now
      }
    case '5':
      // For 5min data, show last 7 days
      return {
        from: now - (7 * 24 * 3600),       // 7 days ago
        to: now
      }
    case '3':
      // For 3min data, show last 5 days
      return {
        from: now - (5 * 24 * 3600),       // 5 days ago
        to: now
      }
    case '2':
      // For 2min data, show last 3 days
      return {
        from: now - (3 * 24 * 3600),       // 3 days ago
        to: now
      }
    case '1':
      // For 1min data, show last 2 days
      return {
        from: now - (2 * 24 * 3600),       // 2 days ago
        to: now
      }
    default:
      return {
        from: now - (7 * 24 * 3600),       // 7 days ago
        to: now
      }
  }
}

// Calculate how much historical data to load in each batch
const getHistoricalBatchSize = (timeframe: Timeframe): number => {
  const oneDay = 24 * 3600
  
  switch (timeframe) {
    case '1D':
      return 180 * oneDay    // 6 months for daily
    case '60':
      return 30 * oneDay     // 30 days for hourly  
    case '30':
      return 30 * oneDay     // 30 days for 30min
    case '15':
      return 21 * oneDay     // 3 weeks for 15min
    case '5':
      return 14 * oneDay     // 2 weeks for 5min
    case '3':
    case '2':
      return 0               // No infinite scroll for limited data timeframes
    case '1':
      return 7 * oneDay      // 1 week for 1min
    default:
      return 14 * oneDay
  }
}

const LABEL_COLOR: Record<string, string> = {
  Bullish: '#00E676',      // bright green
  Bearish: '#FF1744',      // bright red
  Neutral: '#9CA3AF',      // grey
  'Exit Bullish': '#FFA726',  // orange for bullish exits
  'Exit Bearish': '#42A5F5',  // blue for bearish exits
}

function makeTickMarkFormatter() {
  // Use UTC formatters to match the data
  const dFmt = new Intl.DateTimeFormat('en-US', { 
    timeZone: 'Asia/Kolkata',
    day: '2-digit', 
    month: 'short' 
  })
  const tFmt = new Intl.DateTimeFormat('en-US', { 
    timeZone: 'Asia/Kolkata',
    hour: '2-digit', 
    minute: '2-digit', 
    hour12: false 
  })
  let lastDayKey: string | null = null

  return (unixSec: number) => {
    const d = new Date(unixSec * 1000)
    const dayKey = `${d.getUTCFullYear()}-${d.getUTCMonth() + 1}-${d.getUTCDate()}`
    const timeTxt = tFmt.format(d)
    
    // Show date on first tick of the day
    if (lastDayKey !== dayKey) {
      lastDayKey = dayKey
      return `${dFmt.format(d)} ${timeTxt}`
    }
    return timeTxt
  }
}

// Fetch chart bars
async function fetchBars(symbol: string, timeframe: Timeframe, from?: number, to?: number): Promise<Bar[]> {
  const timeRange = from && to ? { from, to } : getInitialTimeRange(timeframe)
  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/tradingview-api'
  const url = `${API_BASE_URL}/history?symbol=${encodeURIComponent(symbol)}&from=${timeRange.from}&to=${timeRange.to}&resolution=${timeframe}`
  console.log(`Fetching bars: ${url}`)
  
  const res = await fetch(url, { cache: 'no-store' })
  if (!res.ok) {
    console.error(`Failed to fetch bars: ${res.status} ${res.statusText}`)
    return []
  }
  
  let data: any
  try { 
    data = await res.json() 
  } catch (e) { 
    console.error('Failed to parse bars JSON:', e)
    return [] 
  }

  // Check for error response
  if (data && data.s === 'error') {
    console.error(`Backend error for ${timeframe}min:`, data.errmsg || 'Unknown error')
    console.log('Full error response:', data)
    return []
  }
  
  // Handle TradingView format
  if (data && data.s === 'ok' && Array.isArray(data.t)) {
    const bars = data.t.map((t: number, i: number) => ({
      time: t,
      open: Number(data.o[i]),
      high: Number(data.h[i]),
      low: Number(data.l[i]),
      close: Number(data.c[i]),
    }))
    console.log(`Fetched ${bars.length} bars for ${timeframe}min`)
    return bars
  }
  
  console.log('No bars data found in response:', data)
  return []
}

// Fetch user-created labels only
async function fetchUserLabels(symbol: string, timeframe: Timeframe, from?: number, to?: number): Promise<any[]> {
  const timeRange = from && to ? { from, to } : getInitialTimeRange(timeframe)
  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/tradingview-api'
  const url = `${API_BASE_URL}/marks?symbol=${encodeURIComponent(symbol)}&resolution=${timeframe}&from=${timeRange.from}&to=${timeRange.to}&include_neutral=true`
  console.log(`Fetching labels: ${url}`)
  
  const res = await fetch(url, { cache: 'no-store' })
  if (!res.ok) {
    console.error(`Failed to fetch labels: ${res.status} ${res.statusText}`)
    return []
  }
  
  let data: any
  try { 
    data = await res.json() 
  } catch (e) { 
    console.error('Failed to parse labels JSON:', e)
    return [] 
  }

  if (data && data.marks && Array.isArray(data.marks)) {
    const labels = data.marks.map((mark: any) => {
      // Parse the correct label from text field, not the backend's single character label
      const fullLabel = mark.text?.split(' | ')[0] || 'Unknown'
      const confidence = parseFloat(mark.text?.split('p=')[1]) || 100
      
      return {
        ...mark,
        ts: mark.time,
        label: fullLabel, // Override the backend's single character with full label
        confidence
      }
    })
    console.log(`Fetched ${labels.length} labels for ${timeframe}min`)
    return labels
  }
  
  console.log('No labels data found in response:', data)
  return []
}

// Convert labels to TradingView markers
function createMarkers(labels: any[], bars: Bar[], timeframe: Timeframe): SeriesMarker<Time>[] {
  if (!bars.length) {
    console.log('No bars available for markers')
    return []
  }
  
  const markers: SeriesMarker<Time>[] = []
  console.log(`Creating markers from ${labels.length} labels and ${bars.length} bars`)
  
  // Dynamic tolerance based on timeframe (half the bar duration)
  const timeframeTolerance: Record<Timeframe, number> = {
    '1': 30,     // 30 seconds for 1min
    '2': 60,     // 60 seconds for 2min
    '3': 90,     // 90 seconds for 3min
    '5': 150,    // 150 seconds for 5min
    '15': 450,   // 450 seconds for 15min
    '30': 900,   // 900 seconds for 30min
    '60': 1800,  // 1800 seconds for 1hour
    '1D': 43200  // 12 hours for 1day
  }
  const tolerance = timeframeTolerance[timeframe] || 60
  
  for (const label of labels) {
    // Find the exact bar or closest one
    const targetTime = label.ts
    
    // First try exact match
    let bar = bars.find(b => b.time === targetTime)
    
    // If no exact match, find nearest
    if (!bar) {
      let nearestBar = null
      let minDiff = Infinity
      
      for (const b of bars) {
        const diff = Math.abs(b.time - targetTime)
        if (diff < minDiff && diff < tolerance) {
          minDiff = diff
          nearestBar = b
        }
      }
      
      if (nearestBar) {
        console.log(`Label time ${targetTime} matched to bar at ${nearestBar.time} (diff: ${minDiff}s)`)
        bar = nearestBar
      }
    }
    
    if (!bar) {
      console.log(`No bar found for label timestamp: ${targetTime} (${new Date(targetTime * 1000).toISOString()})`)
      continue
    }

    const txt = label.label || 'Label'
    const confidence = Math.round(label.confidence || 100)
    
    // Position logic: Bullish entries below, everything else above
    const pos = /^bullish$/i.test(txt) ? 'belowBar' : 'aboveBar'
    const color = LABEL_COLOR[txt] || LABEL_COLOR['Neutral']

    markers.push({
      time: bar.time as Time,
      position: pos as any,
      shape: 'circle' as const,
      color,
      text: `${txt} (${confidence}%)`,
      size: 1,
    })
  }

  console.log(`Created ${markers.length} markers`)
  return markers.sort((a, b) => Number(a.time) - Number(b.time))
}

const CustomChartWithMLLabels: React.FC<CustomChartProps> = ({
  symbol = DEFAULT_SYMBOL,
  timeframe = DEFAULT_TF,
  chartType = DEFAULT_TYPE,
  height = 520,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const lineRef = useRef<ISeriesApi<'Line'> | null>(null)
  
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dataLoaded, setDataLoaded] = useState(false)
  
  // Infinite scrolling state
  const [isLoadingOlder, setIsLoadingOlder] = useState(false)
  const [hasMoreData, setHasMoreData] = useState(true)
  
  // Context menu state
  const [menuOpen, setMenuOpen] = useState(false)
  const [menuXY, setMenuXY] = useState<{ x: number; y: number }>({ x: 0, y: 0 })
  const [contextTimestamp, setContextTimestamp] = useState<number | null>(null)
  const menuRef = useRef<HTMLDivElement | null>(null)

  // Store current data for refresh
  const currentBarsRef = useRef<Bar[]>([])
  
  // Refs for infinite scrolling state (to avoid closure issues)
  const oldestTimestampRef = useRef<number | null>(null)
  const hasMoreDataRef = useRef<boolean>(true)
  const isLoadingOlderRef = useRef<boolean>(false)
  
  // Load older historical data for infinite scrolling
  const loadOlderData = async () => {
    if (!chartRef.current || !candleRef.current || !lineRef.current || 
        !oldestTimestampRef.current || isLoadingOlderRef.current || !hasMoreDataRef.current) {
      return
    }
    
    const batchSize = getHistoricalBatchSize(timeframe)
    if (batchSize === 0) {
      // No infinite scroll for this timeframe
      return
    }
    
    setIsLoadingOlder(true)
    isLoadingOlderRef.current = true
    console.log('[INFINITE] Loading older data before timestamp:', oldestTimestampRef.current)
    
    try {
      const fromTime = oldestTimestampRef.current - batchSize
      const toTime = oldestTimestampRef.current - 1
      
      console.log(`[INFINITE] Fetching ${timeframe} data from ${fromTime} to ${toTime}`)
      
      // Fetch older bars and labels
      const [olderBars, olderLabels] = await Promise.all([
        fetchBars(symbol, timeframe, fromTime, toTime),
        fetchUserLabels(symbol, timeframe, fromTime, toTime)
      ])
      
      console.log(`[INFINITE] Got ${olderBars.length} older bars and ${olderLabels.length} older labels`)
      
      if (olderBars.length === 0) {
        console.log('[INFINITE] No more data available')
        setHasMoreData(false)
        hasMoreDataRef.current = false
        return
      }
      
      // Merge with existing data
      const allBars = [...olderBars, ...currentBarsRef.current]
      currentBarsRef.current = allBars
      
      // Update chart with all data (TradingView will handle deduplication)
      candleRef.current.setData(allBars as unknown as CandlestickData[])
      lineRef.current.setData(allBars.map(b => ({ 
        time: b.time as Time, 
        value: b.close 
      })) as LineData[])
      
      // Update markers with all labels
      const allLabels = [...olderLabels, ...await fetchUserLabels(symbol, timeframe, oldestTimestampRef.current, currentBarsRef.current[currentBarsRef.current.length - 1]?.time)]
      const markers = createMarkers(allLabels, allBars, timeframe)
      candleRef.current.setMarkers(markers)
      lineRef.current.setMarkers(markers)
      
      // Update oldest timestamp
      if (olderBars.length > 0) {
        oldestTimestampRef.current = olderBars[0].time
      }
      
      console.log(`[INFINITE] Successfully loaded ${olderBars.length} older bars`)
    } catch (error) {
      console.error('[INFINITE] Failed to load older data:', error)
    } finally {
      setIsLoadingOlder(false)
      isLoadingOlderRef.current = false
    }
  }

  // Create chart once
  useEffect(() => {
    if (!containerRef.current || chartRef.current) return

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: { background: { color: '#0e1220' }, textColor: '#d1d4dc' },
      grid: { vertLines: { color: '#1e222d' }, horzLines: { color: '#1e222d' } },
      timeScale: {
        borderColor: '#2b3245',
        timeVisible: true,
        secondsVisible: false,
        tickMarkFormatter: makeTickMarkFormatter(),
      },
      rightPriceScale: { borderColor: '#2b3245' },
      crosshair: { mode: 0 },
    })
    
    chartRef.current = chart

    // Set up scroll detection for infinite scrolling
    chart.timeScale().subscribeVisibleTimeRangeChange((newRange) => {
      // Get current values from refs to avoid closure issues
      const currentOldest = oldestTimestampRef.current
      const currentBars = currentBarsRef.current
      const currentHasMore = hasMoreDataRef.current
      const currentLoading = isLoadingOlderRef.current
      
      if (!newRange || !currentBars.length || !currentOldest) {
        // Only log occasionally to avoid spam
        if (Math.random() < 0.1) {
          console.log('[SCROLL] Skipping scroll detection:', { 
            hasRange: !!newRange, 
            hasBars: currentBars.length, 
            hasOldest: !!currentOldest,
            oldestValue: currentOldest 
          })
        }
        return
      }
      
      const visibleFromTime = typeof newRange.from === 'number' ? newRange.from : Number(newRange.from)
      const visibleToTime = typeof newRange.to === 'number' ? newRange.to : Number(newRange.to)
      const firstBarTime = currentBars[0]?.time || 0
      
      console.log('[SCROLL] Range changed:', { 
        visibleFrom: visibleFromTime, 
        visibleTo: visibleToTime, 
        firstBar: firstBarTime,
        hasMore: currentHasMore,
        loading: currentLoading
      })
      
      // Check if user scrolled close to the beginning (within 20% of visible range)
      const rangeSize = visibleToTime - visibleFromTime
      const threshold = firstBarTime + (rangeSize * 0.2)
      
      if (visibleFromTime <= threshold && currentHasMore && !currentLoading) {
        console.log('[INFINITE] User scrolled near beginning, loading older data...')
        loadOlderData()
      }
    })

    candleRef.current = chart.addCandlestickSeries({
      upColor: '#26a69a', downColor: '#ef5350',
      borderUpColor: '#26a69a', borderDownColor: '#ef5350',
      wickUpColor: '#26a69a', wickDownColor: '#ef5350',
    })
    
    lineRef.current = chart.addLineSeries({ 
      priceLineVisible: false, 
      color: '#4da3ff',
      visible: false 
    })

    // Right-click context menu
    const onContextMenu = (e: MouseEvent) => {
      e.preventDefault()
      console.log('[MENU] Right-click at:', e.clientX, e.clientY)
      
      // Get timestamp from coordinate
      const rect = containerRef.current!.getBoundingClientRect()
      const x = e.clientX - rect.left
      const timeCoordinate = chart.timeScale().coordinateToTime(x)
      
      if (timeCoordinate !== null) {
        // Ensure we're working with seconds (not milliseconds)
        let clickedTime = typeof timeCoordinate === 'number' ? timeCoordinate : Number(timeCoordinate)
        
        // If the value is too large, it's likely milliseconds
        if (clickedTime > 10000000000) {
          clickedTime = Math.floor(clickedTime / 1000)
          console.log('[MENU] Converted from milliseconds to seconds')
        }
        
        console.log('[MENU] Raw clicked time:', clickedTime)
        
        // Find the nearest actual bar timestamp
        const bars = currentBarsRef.current
        if (bars.length > 0) {
          // Debug: Show what timestamp we're looking for
          console.log('[MENU] Looking for bar near timestamp:', new Date(clickedTime * 1000).toISOString())
          
          let nearestBar = bars[0]
          let nearestIndex = 0
          let minDiff = Math.abs(bars[0].time - clickedTime)
          
          bars.forEach((bar, index) => {
            const diff = Math.abs(bar.time - clickedTime)
            if (diff < minDiff) {
              minDiff = diff
              nearestBar = bar
              nearestIndex = index
            }
          })
          
          // Show nearby bars for debugging
          const start = Math.max(0, nearestIndex - 2)
          const end = Math.min(bars.length - 1, nearestIndex + 2)
          console.log('[MENU] Nearby bars:')
          for (let i = start; i <= end; i++) {
            const isNearest = i === nearestIndex ? '<<< SELECTED' : ''
            console.log(`  [${i}] ${bars[i].time} - ${new Date(bars[i].time * 1000).toISOString()} ${isNearest}`)
          }
          
          setContextTimestamp(nearestBar.time)
          console.log('[MENU] Snapped to bar index:', nearestIndex, 'timestamp:', nearestBar.time, 'diff:', minDiff, 'seconds')
        } else {
          setContextTimestamp(clickedTime)
          console.log('[MENU] No bars to snap to, using raw timestamp:', clickedTime)
        }
      } else {
        setContextTimestamp(null)
        console.log('[MENU] Could not capture timestamp')
      }
      
      setMenuXY({ x: e.clientX, y: e.clientY })
      setMenuOpen(true)
    }
    
    containerRef.current.addEventListener('contextmenu', onContextMenu)

    // Close menu on outside click
    const onDocumentClick = (e: Event) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('click', onDocumentClick)

    // Resize handler
    const onResize = () => {
      if (!containerRef.current || !chartRef.current) return
      chartRef.current.applyOptions({ width: containerRef.current.clientWidth })
    }
    window.addEventListener('resize', onResize)

    return () => {
      containerRef.current?.removeEventListener('contextmenu', onContextMenu)
      document.removeEventListener('click', onDocumentClick)
      window.removeEventListener('resize', onResize)
    }
  }, [height])

  // Toggle chart type
  useEffect(() => {
    if (!candleRef.current || !lineRef.current) return
    
    const showCandle = chartType === 'candle'
    candleRef.current.applyOptions({ visible: showCandle })
    lineRef.current.applyOptions({ visible: !showCandle })
  }, [chartType])

  // Load data when symbol/timeframe changes
  useEffect(() => {
    let cancelled = false
    
    const loadData = async () => {
      if (!chartRef.current || !candleRef.current || !lineRef.current) return
      
      setLoading(true)
      setError(null)
      setDataLoaded(false)

      try {
        console.log(`[LOAD] Loading data for ${symbol} ${timeframe}min...`)
        
        // Reset infinite scroll state
        setHasMoreData(true)
        setIsLoadingOlder(false)
        oldestTimestampRef.current = null
        hasMoreDataRef.current = true
        isLoadingOlderRef.current = false
        
        // Fetch bars and labels in parallel
        const [bars, labels] = await Promise.all([
          fetchBars(symbol, timeframe),
          fetchUserLabels(symbol, timeframe)
        ])

        if (cancelled) return

        console.log(`[LOAD] Got ${bars.length} bars and ${labels.length} labels`)

        if (bars.length === 0) {
          setError(`No chart data available for ${timeframe}min timeframe`)
          return
        }

        // Store bars for refresh
        currentBarsRef.current = bars
        
        // Set oldest timestamp for infinite scrolling
        if (bars.length > 0) {
          oldestTimestampRef.current = bars[0].time
          console.log(`[LOAD] Set oldest timestamp to ${bars[0].time} (${new Date(bars[0].time * 1000).toISOString()})`)
        }

        // Set chart data
        candleRef.current.setData(bars as unknown as CandlestickData[])
        lineRef.current.setData(bars.map(b => ({ 
          time: b.time as Time, 
          value: b.close 
        })) as LineData[])

        // Create and set markers
        const markers = createMarkers(labels, bars, timeframe)
        candleRef.current.setMarkers(markers)
        lineRef.current.setMarkers(markers)

        // Fit content
        chartRef.current.timeScale().fitContent()
        setDataLoaded(true)

      } catch (err: any) {
        if (!cancelled) {
          console.error('[LOAD] Failed to load chart data:', err)
          setError(err?.message || 'Failed to load chart data')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    loadData()
    return () => { cancelled = true }
  }, [symbol, timeframe])

  // Refresh markers only
  const refreshMarkers = async () => {
    if (!chartRef.current || !candleRef.current || !lineRef.current || !dataLoaded) {
      console.log('[REFRESH] Cannot refresh - chart not ready')
      return
    }
    
    try {
      console.log('[REFRESH] Refreshing markers...')
      
      // Fetch fresh labels
      const labels = await fetchUserLabels(symbol, timeframe)
      console.log(`[REFRESH] Got ${labels.length} labels`)
      
      // Log a few recent labels to see if new ones are coming through
      const recentLabels = labels.slice(-5).map(l => `${l.ts}: ${l.label}`)
      console.log('[REFRESH] Recent labels:', recentLabels)
      
      // Look for the specific timestamp we just updated
      const updatedLabel = labels.find(l => l.ts === contextTimestamp)
      if (updatedLabel) {
        console.log('[REFRESH] Found updated label:', updatedLabel)
      } else {
        console.log('[REFRESH] Updated label not found for timestamp:', contextTimestamp)
      }
      
      // Use stored bars
      const bars = currentBarsRef.current
      if (bars.length === 0) {
        console.log('[REFRESH] No bars available')
        return
      }
      
      // Create and set new markers
      const markers = createMarkers(labels, bars, timeframe)
      candleRef.current.setMarkers(markers)
      lineRef.current.setMarkers(markers)
      
      // Log recent markers to see if they're being created
      const recentMarkers = markers.slice(-5).map(m => `${m.time}: ${m.text}`)
      console.log('[REFRESH] Recent markers:', recentMarkers)
      
      console.log(`[REFRESH] Updated ${markers.length} markers`)
    } catch (error) {
      console.error('[REFRESH] Failed to refresh markers:', error)
    }
  }

  // Save label
  const saveLabel = async (label: string) => {
    console.log(`[SAVE] Saving ${label} at timestamp:`, contextTimestamp)
    setMenuOpen(false)
    
    if (!contextTimestamp) {
      console.error('[SAVE] No timestamp available')
      return
    }

    try {
      const payload = {
        symbol,
        timeframe,
        timestamp: contextTimestamp,
        label,
        price: null
      }
      console.log('[SAVE] Sending payload:', payload)
      console.log('[SAVE] Timestamp date:', new Date(contextTimestamp * 1000).toISOString())
      
      const response = await fetch('/api/labels', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })

      if (response.ok) {
        const result = await response.json()
        console.log('[SAVE] Label saved successfully:', result)
        
        // Show whether this was an update or new creation
        if (result.message && result.message.includes('Updated')) {
          console.log('[SAVE] ⚠️  UPDATED existing label')
        } else if (result.message && result.message.includes('Created')) {
          console.log('[SAVE] ✅ CREATED new label')
        }
        
        // Refresh markers to show new label
        await refreshMarkers()
      } else {
        const errorText = await response.text()
        console.error('[SAVE] Failed to save label:', errorText)
      }
    } catch (error) {
      console.error('[SAVE] Error saving label:', error)
    }
  }

  // Delete label
  const deleteLabel = async () => {
    console.log('[DELETE] Deleting label at timestamp:', contextTimestamp)
    setMenuOpen(false)
    
    if (!contextTimestamp) {
      console.error('[DELETE] No timestamp available')
      return
    }

    try {
      const response = await fetch('/api/labels', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol,
          timeframe,
          timestamp: contextTimestamp
        })
      })

      if (response.ok) {
        console.log('[DELETE] Label deleted successfully')
        // Refresh markers to remove label
        await refreshMarkers()
      } else {
        const errorText = await response.text()
        console.error('[DELETE] Failed to delete label:', errorText)
      }
    } catch (error) {
      console.error('[DELETE] Error deleting label:', error)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      <div 
        ref={containerRef} 
        style={{ width: '100%', height }}
      />

      {/* Status footer */}
      <div style={{
        padding: '8px 12px',
        borderTop: '1px solid #1e222d',
        fontSize: 12,
        color: '#9aa4bf',
        display: 'flex',
        justifyContent: 'space-between',
      }}>
        <span>{symbol} - {timeframe}min</span>
        <span>
          {loading ? 'Loading...' : 
           isLoadingOlder ? 'Loading older data...' :
           error ? `Error: ${error}` : 
           dataLoaded ? (hasMoreData ? 'Ready (scroll left for more)' : 'Ready (all data loaded)') : 'Initializing...'}
        </span>
      </div>

      {/* Context menu */}
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
          }}
        >
          <div
            style={{ padding: '8px 10px', cursor: 'pointer' }}
            onClick={() => saveLabel('Bullish')}
          >
            ➕ Set Bullish
          </div>
          <div
            style={{ padding: '8px 10px', cursor: 'pointer' }}
            onClick={() => saveLabel('Exit Bullish')}
          >
            🏁 Exit Bullish
          </div>
          <hr style={{ borderColor: '#374151', margin: '4px 6px' }} />
          <div
            style={{ padding: '8px 10px', cursor: 'pointer' }}
            onClick={() => saveLabel('Bearish')}
          >
            ➕ Set Bearish
          </div>
          <div
            style={{ padding: '8px 10px', cursor: 'pointer' }}
            onClick={() => saveLabel('Exit Bearish')}
          >
            🏁 Exit Bearish
          </div>
          <hr style={{ borderColor: '#374151', margin: '4px 6px' }} />
          <div
            style={{ padding: '8px 10px', cursor: 'pointer' }}
            onClick={() => saveLabel('Neutral')}
          >
            ➕ Set Neutral
          </div>
          <hr style={{ borderColor: '#1f2937', margin: '6px 0' }} />
          <div
            style={{ padding: '8px 10px', cursor: 'pointer', color: '#ef4444' }}
            onClick={deleteLabel}
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