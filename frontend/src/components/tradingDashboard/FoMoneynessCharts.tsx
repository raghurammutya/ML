import React from 'react'
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, Legend, CartesianGrid } from 'recharts'
import styles from './MiniChartsPanel.module.css'
import { PANEL_GROUPS } from './analytics'
import type { MoneynessPanelData } from '../../hooks/useFoAnalytics'

interface FoMoneynessChartsProps {
  panels: MoneynessPanelData
  loading: boolean
  variant?: 'default' | 'compact'
}

const formatTime = (timestampSeconds: number) => {
  return new Date(timestampSeconds * 1000).toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

const mergeSeries = (
  lines: { label: string | null; bucket: string; expiry?: string; points: { time: number; value: number }[] }[],
) => {
  const map = new Map<number, Record<string, number | undefined>>()
  lines.forEach((line) => {
    const key = `${line.label ?? line.expiry ?? 'Series'} · ${line.bucket}`
    line.points.forEach((point) => {
      const existing = map.get(point.time) ?? { time: point.time }
      existing[key] = point.value
      map.set(point.time, existing)
    })
  })
  return Array.from(map.values()).sort((a, b) => (a.time as number) - (b.time as number))
}

const FoMoneynessCharts: React.FC<FoMoneynessChartsProps> = ({ panels, loading, variant = 'default' }) => {
  if (loading) {
    return (
      <div className={styles.empty}>
        Loading FO analytics…
      </div>
    )
  }

  const groups = PANEL_GROUPS.filter((group) => group.panelIds.some((id) => panels[id]?.length))

  if (!groups.length) {
    return (
      <div className={styles.empty}>
        No FO analytics data available for the selected symbol/timeframe.
      </div>
    )
  }

  return (
    <div className={variant === 'compact' ? `${styles.wrapper} ${styles.compact}` : styles.wrapper}>
      <div className={styles.panelColumn}>
        {groups.map((group) => (
          <section key={group.id} className={styles.panel}>
            <div className={styles.header}>
              <div className={styles.title}>
                <h3>{group.title}</h3>
                <span className={styles.subtitle}>{group.subtitle}</span>
              </div>
            </div>

            {group.panelIds.map((panelId) => {
              const lines = panels[panelId] ?? []
              if (!lines.length) return null
              const chartData = mergeSeries(lines)
              return (
                <div key={panelId} className={styles.chart} style={{ height: 220 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData} margin={{ top: 10, right: 16, left: 0, bottom: 6 }}>
                      <CartesianGrid stroke="rgba(148, 163, 184, 0.14)" strokeDasharray="3 3" />
                      <XAxis
                        dataKey="time"
                        tickFormatter={(value) => formatTime(Number(value))}
                        stroke="rgba(148, 163, 184, 0.65)"
                        tick={{ fill: 'rgba(148, 163, 184, 0.8)', fontSize: 11 }}
                      />
                      <YAxis
                        stroke="rgba(148, 163, 184, 0.65)"
                        tick={{ fill: 'rgba(148, 163, 184, 0.8)', fontSize: 11 }}
                        domain={['auto', 'auto']}
                      />
                      <Tooltip
                        formatter={(value: number) => value.toFixed(3)}
                        labelFormatter={(label) => formatTime(Number(label))}
                        contentStyle={{ background: '#0f172a', borderRadius: 12, border: '1px solid rgba(148, 163, 184, 0.18)' }}
                      />
                      <Legend />
                      {lines.map((line) => {
                        const seriesKey = `${line.label ?? line.expiry ?? 'Series'} · ${line.bucket}`
                        return (
                        <Line
                          key={seriesKey}
                          dataKey={seriesKey}
                          stroke={line.color}
                          strokeWidth={2}
                          dot={false}
                          type="monotone"
                          isAnimationActive={false}
                        />
                        )
                      })}
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )
            })}
          </section>
        ))}
      </div>
    </div>
  )
}

export default FoMoneynessCharts
