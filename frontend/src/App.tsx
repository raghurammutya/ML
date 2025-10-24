import React, { useEffect, useState } from 'react'
import CustomChartWithMLLabels from './components/CustomChartWithMLLabels'
import Sidebar from './components/Sidebar'
import Header from './components/Header'
import { HealthStatus, CacheStats, LabelDistribution } from './types'
import { fetchHealth, fetchCacheStats } from './services/api'

type Timeframe = '1' | '2' | '3' | '5' | '15' | '30' | '60' | '1D'
type ChartType = 'candle' | 'line'

const App: React.FC = () => {
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [cacheStats, setCacheStats] = useState<CacheStats | null>(null)
  const [labelDistribution] = useState<LabelDistribution | null>(null)

  const supportedTimeframes: Timeframe[] = ['1', '2', '3', '5', '15', '30', '60', '1D']
  const [selectedTimeframe, setSelectedTimeframe] = useState<Timeframe>('5')

  const [chartType, setChartType] = useState<ChartType>('candle')

  // Date/time filter (optional)
  const [fromInput, setFromInput] = useState<string>('') // e.g. 2024-10-01 09:15
  const [toInput, setToInput] = useState<string>('')     // e.g. 2025-03-01 15:30
  const [fromSec, setFromSec] = useState<number | null>(null)
  const [toSec, setToSec] = useState<number | null>(null)

  useEffect(() => {
    fetchData()
    const id = setInterval(fetchData, 30000)
    return () => clearInterval(id)
  }, [])

  const fetchData = async () => {
    try {
      const [h, c] = await Promise.all([fetchHealth(), fetchCacheStats()])
      setHealth(h); setCacheStats(c)
    } catch (e) { /* ignore header errors for now */ }
  }

  const applyRange = () => {
    const parse = (s: string) => {
      if (!s.trim()) return null
      // accept "YYYY-MM-DD HH:mm" or ISO
      const normalized = s.includes('T') ? s : s.replace(' ', 'T') + ':00Z'
      const d = new Date(normalized)
      if (isNaN(d.getTime())) return null
      return Math.floor(d.getTime() / 1000)
    }
    const f = parse(fromInput)
    const t = parse(toInput)
    setFromSec(f)
    setToSec(t)
  }

  const clearRange = () => {
    setFromInput(''); setToInput('')
    setFromSec(null); setToSec(null)
  }

  return (
    <div className="app-container">
      <Header health={health} />

      <div className="main-content">
        <div className="chart-container">


          {/* Top-right controls: timeframe + chart type + date range */}
          <div style={{
            position: 'absolute', top: 12, right: 12, zIndex: 1000,
            background: 'rgba(19, 23, 34, 0.95)', border: '1px solid #2a2e39', borderRadius: 8, padding: 8,
            display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap'
          }}>
            {/* Timeframes */}
            <div style={{ display: 'flex', gap: 4 }}>
              {supportedTimeframes.map(tf => (
                <button key={tf}
                  onClick={() => setSelectedTimeframe(tf)}
                  style={{
                    backgroundColor: selectedTimeframe === tf ? '#26a69a' : '#2a2e39',
                    color: selectedTimeframe === tf ? '#000' : '#d1d4dc',
                    border: 'none', borderRadius: 4, padding: '4px 8px', fontSize: 11, cursor: 'pointer'
                  }}>{tf === '60' ? '1h' : tf === '1D' ? '1D' : `${tf}m`}</button>
              ))}
            </div>

            {/* Chart type */}
            <div style={{ display: 'flex', gap: 4, marginLeft: 6 }}>
              {(['candle', 'line'] as ChartType[]).map(t => (
                <button key={t}
                  onClick={() => setChartType(t)}
                  style={{
                    backgroundColor: chartType === t ? '#26a69a' : '#2a2e39',
                    color: chartType === t ? '#000' : '#d1d4dc',
                    border: 'none', borderRadius: 4, padding: '4px 8px', fontSize: 11, cursor: 'pointer'
                  }}>{t}</button>
              ))}
            </div>

            {/* Date range */}
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <input
                placeholder="From (YYYY-MM-DD HH:mm)"
                value={fromInput}
                onChange={(e) => setFromInput(e.target.value)}
                style={{ background: '#131722', color: '#d1d4dc', border: '1px solid #2a2e39', borderRadius: 4, padding: '4px 8px', width: 180 }}
              />
              <input
                placeholder="To (YYYY-MM-DD HH:mm)"
                value={toInput}
                onChange={(e) => setToInput(e.target.value)}
                style={{ background: '#131722', color: '#d1d4dc', border: '1px solid #2a2e39', borderRadius: 4, padding: '4px 8px', width: 180 }}
              />
              <button onClick={applyRange}
                style={{ background: '#26a69a', color: '#000', border: 'none', borderRadius: 4, padding: '4px 8px', fontSize: 11, cursor: 'pointer' }}>
                Apply
              </button>
              <button onClick={clearRange}
                style={{ background: '#2a2e39', color: '#d1d4dc', border: 'none', borderRadius: 4, padding: '4px 8px', fontSize: 11, cursor: 'pointer' }}>
                Clear
              </button>
            </div>
          </div>

          <CustomChartWithMLLabels
            symbol="NIFTY50"
            timeframe={selectedTimeframe}
            chartType={chartType}
            height={520}
            fromSec={fromSec}
            toSec={toSec}
          />
        </div>

        <Sidebar
          health={health}
          cacheStats={cacheStats}
          labelDistribution={labelDistribution}
          selectedTimeframe={selectedTimeframe}
        />
      </div>
    </div>
  )
}

export default App
