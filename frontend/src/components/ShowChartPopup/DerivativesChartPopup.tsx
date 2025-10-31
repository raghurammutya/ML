import React, { useState, useEffect, useRef, useCallback } from 'react'
import { createChart, IChartApi, Time, CandlestickData, ISeriesApi } from 'lightweight-charts'

interface DerivativesChartPopupProps {
  underlying: string
  strike?: number // For vertical panel context
  bucket?: string // For horizontal panel context (ATM, OTM1, etc.)
  expiry: string
  timestamp: number
  onClose: () => void
  onPin?: (pinnedState: PinnedCursorState) => void
}

interface PinnedCursorState {
  cursorUtc: string
  timeframe: string
  playbackSpeed: number
  isFollowingMain: boolean
  windowStartUtc?: string
  windowEndUtc?: string
}

interface HistoricalCandle {
  o: number
  h: number
  l: number
  c: number
  v: number
}

interface HistoricalMetrics {
  iv: number
  delta: number
  gamma: number
  theta: number
  vega: number
  premium: number
  oi: number
  oi_delta: number
  bid?: number
  ask?: number
  last?: number
}

interface HistoricalResponse {
  timestamps: string[]
  candles: HistoricalCandle[]
  metrics?: HistoricalMetrics[]
}

interface OIViewData {
  strike: number
  putOI: number
  callOI: number
  putOIChange: number
  callOIChange: number
}

const DerivativesChartPopup: React.FC<DerivativesChartPopupProps> = ({
  underlying,
  strike,
  bucket,
  expiry,
  timestamp,
  onClose,
  onPin
}) => {
  const [activeTab, setActiveTab] = useState<'candles' | 'moneyness' | 'oi' | 'metrics'>('candles')
  const [isPinned, setIsPinned] = useState(false)
  const [isLive] = useState(true)
  const [historicalData, setHistoricalData] = useState<HistoricalResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedExpiries] = useState<string[]>([expiry])


  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  // Format timestamp for display in IST
  const formatTimestamp = (ts: number) => {
    return new Date(ts * 1000).toLocaleString('en-IN', {
      timeZone: 'Asia/Kolkata',
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    })
  }

  // Format strike for display
  const formatStrike = (strike: number) => {
    return strike.toLocaleString('en-IN')
  }

  // Get display context based on whether this is strike-based or bucket-based
  const getDisplayContext = () => {
    if (strike) {
      return `${underlying} ${formatStrike(strike)} ${expiry}`
    } else if (bucket) {
      return `${underlying} ${bucket} ${expiry}`
    }
    return `${underlying} ${expiry}`
  }

  // Fetch historical data for the specific strike/bucket + expiry combination
  const fetchHistoricalData = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)

      const params = new URLSearchParams({
        underlying,
        expiry,
        timeframe: '1m',
        start: new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString(), // 4 hours ago
        end: new Date().toISOString()
      })

      // Add strike or bucket parameter
      if (strike) {
        params.append('strike', strike.toString())
      } else if (bucket) {
        params.append('bucket', bucket)
      }

      const response = await fetch(`/historical/series?${params}`)

      if (!response.ok) {
        throw new Error(`Failed to fetch data: ${response.statusText}`)
      }

      const data: HistoricalResponse = await response.json()
      setHistoricalData(data)

      // Update chart with data
      if (chartRef.current && candleSeriesRef.current && data.candles.length > 0) {
        const chartData = data.timestamps.map((ts, i) => ({
          time: Math.floor(new Date(ts).getTime() / 1000) as Time,
          open: data.candles[i].o,
          high: data.candles[i].h,
          low: data.candles[i].l,
          close: data.candles[i].c
        }))

        candleSeriesRef.current.setData(chartData as CandlestickData[])
        chartRef.current.timeScale().fitContent()
      }

    } catch (err) {
      console.error('Failed to fetch historical data:', err)
      setError(err instanceof Error ? err.message : 'Failed to fetch data')
    } finally {
      setLoading(false)
    }
  }, [underlying, strike, bucket, expiry])

  // Initialize chart
  useEffect(() => {
    if (!chartContainerRef.current) return

    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: 300,
      layout: { background: { color: '#0e1220' }, textColor: '#d1d4dc' },
      grid: { vertLines: { color: '#1e222d' }, horzLines: { color: '#1e222d' } },
      timeScale: {
        borderColor: '#2b3245',
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: { borderColor: '#2b3245' },
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
    })

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderUpColor: '#26a69a',
      borderDownColor: '#ef5350',
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    })

    chartRef.current = chart
    candleSeriesRef.current = candleSeries

    const onResize = () => {
      if (chartContainerRef.current && chart) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', onResize)

    return () => {
      window.removeEventListener('resize', onResize)
      chart.remove()
    }
  }, [])

  // Setup WebSocket subscription for live updates
  useEffect(() => {
    if (!isPinned && isLive) {
      const wsUrl = `ws://localhost:8081/ws/fo`
      const ws = new WebSocket(wsUrl)

      ws.onopen = () => {
        console.log('WebSocket connected for derivatives popup')
        // Subscribe to popup-specific updates
        const subscriptionMessage: {
          action: string
          underlying: string
          expiry: string
          timeframe: string
          strike?: number
          bucket?: string
        } = {
          action: 'subscribe_popup',
          underlying,
          expiry,
          timeframe: '1m',
          ...(strike ? { strike } : {}),
          ...(bucket ? { bucket } : {})
        }
        ws.send(JSON.stringify(subscriptionMessage))


        if (strike) {
          subscriptionMessage.strike = strike
        } else if (bucket) {
          subscriptionMessage.bucket = bucket
        }

        ws.send(JSON.stringify(subscriptionMessage))
      }

      ws.onmessage = (event) => {
        try {
          // Skip non-JSON messages like "ping"
          if (typeof event.data !== 'string' || !event.data.startsWith('{')) {
            return
          }
          const data = JSON.parse(event.data)
          if (data.type === 'popup_update') {
            // Update chart with new candle data
            if (chartRef.current && candleSeriesRef.current && data.candle) {
              const newCandle: CandlestickData = {
                time: Math.floor(new Date(data.timestamp).getTime() / 1000) as Time,
                open: data.candle.o,
                high: data.candle.h,
                low: data.candle.l,
                close: data.candle.c
              }
              candleSeriesRef.current.update(newCandle)
            }
          }
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err)
        }
      }

      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
      }

      wsRef.current = ws

      return () => {
        ws.close()
      }
    }
  }, [isPinned, isLive, underlying, strike, bucket, expiry])

  // Load initial data
  useEffect(() => {
    fetchHistoricalData()
  }, [fetchHistoricalData])

  // Handle pin toggle
  const handlePinToggle = () => {
    const newPinnedState = !isPinned
    setIsPinned(newPinnedState)

    if (newPinnedState && onPin) {
      // Create pinned cursor state
      const pinnedState: PinnedCursorState = {
        cursorUtc: new Date().toISOString(),
        timeframe: '1m',
        playbackSpeed: 1.0,
        isFollowingMain: false,
        windowStartUtc: new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString(),
        windowEndUtc: new Date().toISOString()
      }
      onPin(pinnedState)
    }
  }

  // Generate mock OI data for OI View tab
  const generateOIData = (): OIViewData[] => {
    if (!strike) return []

    const data: OIViewData[] = []
    for (let i = -5; i <= 5; i++) {
      const strikeLevel = strike + (i * 50) // 50 point intervals
      data.push({
        strike: strikeLevel,
        putOI: Math.random() * 10000 + 5000,
        callOI: Math.random() * 10000 + 5000,
        putOIChange: (Math.random() - 0.5) * 2000,
        callOIChange: (Math.random() - 0.5) * 2000,
      })
    }
    return data
  }

  const renderTabContent = () => {
    if (loading) {
      return (
        <div className="flex items-center justify-center h-64">
          <div className="text-gray-400">Loading...</div>
        </div>
      )
    }

    if (error) {
      return (
        <div className="flex items-center justify-center h-64">
          <div className="text-red-400">Error: {error}</div>
        </div>
      )
    }

    switch (activeTab) {
      case 'candles':
        return (
          <div ref={chartContainerRef} className="w-full h-80" />
        )

      case 'moneyness':
        return (
          <div className="p-4">
            <div className="text-gray-400 text-sm mb-4">
              Cross-expiry moneyness analysis
            </div>
            <div className="space-y-2">
              {selectedExpiries.map((exp: string) => (
                <div key={exp} className="flex items-center justify-between bg-gray-800 p-3 rounded">
                  <div className="text-sm">{exp}</div>
                  <div className="text-lg font-mono">
                    {bucket || `Strike ${strike}`}
                  </div>
                </div>
              ))}

            </div>
            <div className="mt-4 text-gray-500 text-sm">
              Moneyness visualization coming soon...
            </div>
          </div>
        )

      case 'oi':
        const oiData = generateOIData()
        return (
          <div className="p-4">
            <div className="text-gray-400 text-sm mb-4">
              Strike-by-strike OI visualization
            </div>
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {oiData.map(item => (
                <div key={item.strike} className="grid grid-cols-5 gap-2 text-xs bg-gray-800 p-2 rounded">
                  <div className="font-mono">{formatStrike(item.strike)}</div>
                  <div className="text-green-400">{item.callOI.toFixed(0)}</div>
                  <div className="text-red-400">{item.putOI.toFixed(0)}</div>
                  <div className={item.callOIChange >= 0 ? 'text-green-400' : 'text-red-400'}>
                    {item.callOIChange >= 0 ? '+' : ''}{item.callOIChange.toFixed(0)}
                  </div>
                  <div className={item.putOIChange >= 0 ? 'text-green-400' : 'text-red-400'}>
                    {item.putOIChange >= 0 ? '+' : ''}{item.putOIChange.toFixed(0)}
                  </div>
                </div>
              ))}
            </div>
            <div className="grid grid-cols-5 gap-2 text-xs text-gray-400 mt-2 p-2">
              <div>Strike</div>
              <div>Call OI</div>
              <div>Put OI</div>
              <div>Call Δ</div>
              <div>Put Δ</div>
            </div>
          </div>
        )

      case 'metrics':
        const latestMetrics = historicalData?.metrics?.[historicalData.metrics.length - 1]
        return (
          <div className="p-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-gray-800 p-3 rounded">
                <div className="text-xs text-gray-400 mb-1">IV</div>
                <div className="text-lg font-mono">
                  {latestMetrics?.iv.toFixed(3) || 'N/A'}
                </div>
              </div>
              <div className="bg-gray-800 p-3 rounded">
                <div className="text-xs text-gray-400 mb-1">Delta</div>
                <div className="text-lg font-mono">
                  {latestMetrics?.delta.toFixed(3) || 'N/A'}
                </div>
              </div>
              <div className="bg-gray-800 p-3 rounded">
                <div className="text-xs text-gray-400 mb-1">Gamma</div>
                <div className="text-lg font-mono">
                  {latestMetrics?.gamma.toFixed(4) || 'N/A'}
                </div>
              </div>
              <div className="bg-gray-800 p-3 rounded">
                <div className="text-xs text-gray-400 mb-1">Theta</div>
                <div className="text-lg font-mono">
                  {latestMetrics?.theta.toFixed(3) || 'N/A'}
                </div>
              </div>
              <div className="bg-gray-800 p-3 rounded">
                <div className="text-xs text-gray-400 mb-1">Vega</div>
                <div className="text-lg font-mono">
                  {latestMetrics?.vega.toFixed(3) || 'N/A'}
                </div>
              </div>
              <div className="bg-gray-800 p-3 rounded">
                <div className="text-xs text-gray-400 mb-1">Premium</div>
                <div className="text-lg font-mono">
                  ₹{latestMetrics?.premium.toFixed(2) || 'N/A'}
                </div>
              </div>
              <div className="bg-gray-800 p-3 rounded">
                <div className="text-xs text-gray-400 mb-1">OI</div>
                <div className="text-lg font-mono">
                  {latestMetrics?.oi.toLocaleString('en-IN') || 'N/A'}
                </div>
              </div>
              <div className="bg-gray-800 p-3 rounded">
                <div className="text-xs text-gray-400 mb-1">OI Δ</div>
                <div className="text-lg font-mono">
                  {latestMetrics?.oi_delta != null
                    ? `${latestMetrics.oi_delta >= 0 ? '+' : ''}${latestMetrics.oi_delta.toLocaleString('en-IN')}`
                    : 'N/A'}
                </div>
              </div>
            </div>
          </div>
        )

      default:
        return null
    }
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-gray-900 border border-gray-700 rounded-lg w-[800px] h-[600px] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <div className="flex items-center space-x-4">
            <div className="text-lg font-medium text-white">
              {getDisplayContext()}
            </div>
            <div className="text-sm text-gray-400">
              {formatTimestamp(timestamp)}
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={handlePinToggle}
              className={`px-3 py-1 rounded text-sm ${isPinned
                ? 'bg-blue-600 text-white'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                }`}
            >
              {isPinned ? '📌 Pinned' : 'Pin'}
            </button>

            <div className={`px-2 py-1 rounded text-xs ${isLive ? 'bg-green-600 text-white' : 'bg-gray-600 text-gray-300'
              }`}>
              {isLive ? '🟢 Live' : '⏸️ Paused'}
            </div>

            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white p-1"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-700">
          {[
            { key: 'candles', label: 'Candles' },
            { key: 'moneyness', label: 'Moneyness' },
            { key: 'oi', label: 'OI View' },
            { key: 'metrics', label: 'Metrics' }
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key as any)}
              className={`px-4 py-2 text-sm font-medium ${activeTab === tab.key
                ? 'text-blue-400 border-b-2 border-blue-400'
                : 'text-gray-400 hover:text-gray-300'
                }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden">
          {renderTabContent()}
        </div>
      </div>
    </div>
  )
}

export default DerivativesChartPopup