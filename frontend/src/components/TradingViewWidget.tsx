import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'

interface TradingViewWidgetProps {
  symbol: string
  interval: string
  onIntervalChange?: (interval: string) => void
}

declare global {
  interface Window {
    TradingView: any
  }
}

const TradingViewWidget: React.FC<TradingViewWidgetProps> = ({ 
  symbol, 
  interval
}) => {
  const containerRef = useRef<HTMLDivElement>(null)
  const [currentData, setCurrentData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const normalizedSymbol = useMemo(() => symbol.trim(), [symbol])
  const tradingViewSymbol = useMemo(() => {
    if (!normalizedSymbol) return 'NSE:NIFTY50'
    return normalizedSymbol.includes(':') ? normalizedSymbol : `NSE:${normalizedSymbol}`
  }, [normalizedSymbol])
  const historySymbol = useMemo(() => {
    if (!normalizedSymbol) return 'NIFTY50'
    const compact = normalizedSymbol.includes(':') ? normalizedSymbol.split(':').pop() ?? normalizedSymbol : normalizedSymbol
    return compact.replace(/\s+/g, '').toUpperCase()
  }, [normalizedSymbol])

  const fetchCustomData = useCallback(async () => {
    try {
      const endTime = 1753457340   // July 25, 2025 15:29
      const startTime = 1752845100 // July 18, 2025 13:25
      
      const baseUrl = import.meta.env.VITE_API_BASE_URL || '/tradingview-api'
      const params = `symbol=${encodeURIComponent(historySymbol)}&from=${startTime}&to=${endTime}&resolution=${interval}`
      const [historyRes, marksRes] = await Promise.all([
        fetch(`${baseUrl}/history?${params}`),
        fetch(`${baseUrl}/marks?${params}`)
      ])

      if (historyRes.ok && marksRes.ok) {
        const historyData = await historyRes.json()
        const marksData = await marksRes.json()
        
        setCurrentData({
          history: historyData,
          marks: marksData
        })
      } else {
        setCurrentData(null)
      }
    } catch (fetchError) {
      console.error('Error fetching custom data:', fetchError)
      setCurrentData(null)
    }
  }, [historySymbol, interval])

  useEffect(() => {
    if (!containerRef.current) return

    // Clean up previous widget
    containerRef.current.innerHTML = ''
    setLoading(true)
    setError(null)
    
    // Create the TradingView widget
    const script = document.createElement('script')
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js'
    script.type = 'text/javascript'
    script.async = true
    script.onload = () => {
      console.log('TradingView script loaded successfully')
      setTimeout(() => setLoading(false), 2000) // Give TradingView time to initialize
    }
    script.onerror = (err) => {
      console.error('Failed to load TradingView script:', err)
      setError('Failed to load TradingView chart. This may be due to mixed content restrictions.')
      setLoading(false)
    }
    script.innerHTML = JSON.stringify({
      "autosize": true,
      "symbol": tradingViewSymbol,
      "interval": interval === "60" ? "60" : interval,
      "timezone": "Asia/Kolkata",
      "theme": "dark",
      "style": "1",
      "locale": "en",
      "enable_publishing": false,
      "allow_symbol_change": false,
      "save_image": false,
      "container_id": "tradingview_widget",
      "hide_side_toolbar": false,
      "studies": [
        "STD;SMA",
        "STD;RSI"
      ],
      "show_popup_button": false,
      "popup_width": "1000",
      "popup_height": "650",
      "support_host": "https://www.tradingview.com"
    })

    const widgetContainer = document.createElement('div')
    widgetContainer.className = 'tradingview-widget-container'
    widgetContainer.style.height = '100%'
    widgetContainer.style.width = '100%'
    
    const widgetDiv = document.createElement('div')
    widgetDiv.id = 'tradingview_widget'
    widgetDiv.style.height = '100%'
    widgetDiv.style.width = '100%'
    
    widgetContainer.appendChild(widgetDiv)
    widgetContainer.appendChild(script)
    
    containerRef.current.appendChild(widgetContainer)

    // Fetch our custom data to display alongside
    fetchCustomData()

    return () => {
      if (containerRef.current) {
        containerRef.current.innerHTML = ''
      }
    }
  }, [fetchCustomData, interval, tradingViewSymbol])

  return (
    <div style={{ height: '100%', position: 'relative' }}>
      {loading && (
        <div className="loading-spinner">
          Loading TradingView chart...
        </div>
      )}
      
      {error && (
        <div style={{
          height: '50%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#131722',
          color: '#ef5350',
          padding: '20px',
          textAlign: 'center'
        }}>
          <div style={{ marginBottom: '20px', fontSize: '16px' }}>{error}</div>
          <div style={{ fontSize: '14px', color: '#787b86' }}>
            Try switching to "Custom Chart (Your Data + ML)" using the toggle above, 
            or access the site via HTTPS if available.
          </div>
        </div>
      )}
      
      {/* TradingView Widget Container */}
      <div 
        ref={containerRef} 
        style={{ height: '85%', width: '100%' }}
      />
      
      {/* ML Labels Summary */}
      {currentData?.marks?.marks && currentData.marks.marks.length > 0 && (
        <div style={{
          position: 'absolute',
          top: '10px',
          right: '10px',
          background: 'rgba(19, 23, 34, 0.9)',
          border: '1px solid #2a2e39',
          borderRadius: '4px',
          padding: '10px',
          fontSize: '12px',
          color: '#d1d4dc',
          zIndex: 10
        }}>
          <div style={{ marginBottom: '5px', fontWeight: 'bold' }}>Recent ML Predictions</div>
          {currentData.marks.marks.slice(-5).reverse().map((mark: any, index: number) => (
            <div key={index} style={{ 
              display: 'flex', 
              alignItems: 'center', 
              marginBottom: '3px' 
            }}>
              <div style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                backgroundColor: mark.color,
                marginRight: '5px'
              }} />
              <span>{mark.text}</span>
            </div>
          ))}
        </div>
      )}
      
      {/* Custom Data Info Panel */}
      <div style={{
        height: '15%',
        background: '#131722',
        borderTop: '1px solid #2a2e39',
        padding: '10px',
        overflow: 'auto'
      }}>
        <div style={{ fontSize: '14px', color: '#d1d4dc' }}>
          <strong>Data Source:</strong> Your TimescaleDB with ML Labels
          {currentData?.history?.s === 'ok' && (
            <span style={{ marginLeft: '20px' }}>
              Data Points: {currentData.history.t?.length || 0} | 
              Latest: ₹{currentData.history.c?.[currentData.history.c.length - 1]?.toFixed(2)}
            </span>
          )}
          {currentData?.marks?.marks && (
            <span style={{ marginLeft: '20px' }}>
              ML Labels: {currentData.marks.marks.length}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

export default TradingViewWidget
