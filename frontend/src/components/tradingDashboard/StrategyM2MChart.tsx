import { useEffect, useMemo, useState } from 'react'
import styles from './StrategyM2MChart.module.css'
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts'
import { useStrategy } from '../../contexts/StrategyContext'
import { useAuth } from '../../contexts/AuthContext'
import { fetchStrategyM2M } from '../../services/strategies'

type TimeframeKey = '1H' | '4H' | '1D' | '1W'

const TIMEFRAME_WINDOWS: Record<TimeframeKey, number> = {
  '1H': 60 * 60,
  '4H': 4 * 60 * 60,
  '1D': 24 * 60 * 60,
  '1W': 7 * 24 * 60 * 60,
}

interface ChartPoint {
  timeLabel: string
  value: number
}

export const StrategyM2MChart = () => {
  const { selectedStrategy } = useStrategy()
  const { accessToken } = useAuth()
  const [timeframe, setTimeframe] = useState<TimeframeKey>('1H')
  const [data, setData] = useState<ChartPoint[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useMemo(() => {
    const strategyId = selectedStrategy?.strategy_id
    if (!strategyId || !accessToken) return null
    return async () => {
      const now = Math.floor(Date.now() / 1000)
      const from = now - TIMEFRAME_WINDOWS[timeframe]
      const candles = await fetchStrategyM2M(accessToken, strategyId, from, now)
      return candles.map((candle) => ({
        timeLabel: new Date(candle.timestamp).toLocaleTimeString('en-IN', {
          hour: '2-digit',
          minute: '2-digit',
        }),
        value: candle.close,
      }))
    }
  }, [selectedStrategy?.strategy_id, accessToken, timeframe])

  useEffect(() => {
    if (!refresh) {
      setData([])
      return
    }
    let cancelled = false
    const load = async () => {
      try {
        setLoading(true)
        setError(null)
        const points = await refresh()
        if (!cancelled) {
          setData(points)
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(err.message || 'Failed to load M2M data')
          setData([])
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    const interval = window.setInterval(load, 60000)
    return () => {
      cancelled = true
      window.clearInterval(interval)
    }
  }, [refresh])

  if (!selectedStrategy) {
    return (
      <div className={styles.wrapper}>
        <div className={styles.empty}>Select a strategy to view M2M history</div>
      </div>
    )
  }

  return (
    <div className={styles.wrapper}>
      <div className={styles.header}>
        <div className={styles.title}>M2M History</div>
        <div className={styles.timeframeGroup}>
          {(Object.keys(TIMEFRAME_WINDOWS) as TimeframeKey[]).map((key) => (
            <button
              type="button"
              key={key}
              className={timeframe === key ? styles.timeframeActive : undefined}
              onClick={() => setTimeframe(key)}
            >
              {key}
            </button>
          ))}
        </div>
      </div>
      {loading && <div className={styles.status}>Updating…</div>}
      {error && !loading && <div className={styles.error}>{error}</div>}
      {!loading && !error && data.length === 0 && <div className={styles.empty}>No data available.</div>}
      {!loading && !error && data.length > 0 && (
        <div className={styles.chart}>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={data}>
              <CartesianGrid stroke="rgba(148, 163, 184, 0.12)" vertical={false} />
              <XAxis dataKey="timeLabel" stroke="rgba(148, 163, 184, 0.6)" />
              <YAxis stroke="rgba(148, 163, 184, 0.6)" />
              <Tooltip
                contentStyle={{
                  background: 'rgba(15, 23, 42, 0.95)',
                  border: '1px solid rgba(148, 163, 184, 0.25)',
                  borderRadius: 12,
                }}
              />
              <Line type="monotone" dataKey="value" stroke="#22d3ee" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

export default StrategyM2MChart
