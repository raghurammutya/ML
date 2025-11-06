import React, { useEffect, useMemo, useState } from 'react'
import { ResponsiveContainer, RadarChart, Radar, PolarGrid, PolarAngleAxis } from 'recharts'
import styles from './MiniChartsPanel.module.css'
import { useMonitorSync } from '../../components/nifty-monitor/MonitorSyncContext'
import {
  RADAR_METRICS,
  fetchHistoryBars,
  HistoryBar,
  nearestPoint,
  PANEL_TEMPLATES,
  ChartPoint,
} from './analytics'

interface OptionsRadarProps {
  symbol: string
  timeframe: string
  width?: number
  values?: Record<string, number | null>
}

const OptionsRadar: React.FC<OptionsRadarProps> = ({ symbol, timeframe, width = 200, values }) => {
  const { crosshairTime } = useMonitorSync()
  const [bars, setBars] = useState<HistoryBar[]>([])

  useEffect(() => {
    if (values) {
      setBars([])
      return () => undefined
    }
    let cancelled = false
    const load = async () => {
      try {
        const data = await fetchHistoryBars(symbol, timeframe)
        if (!cancelled) setBars(data)
      } catch (err) {
        console.error('Failed to load radar data', err)
        if (!cancelled) setBars([])
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [symbol, timeframe, values])

  const latestValues = useMemo(() => {
    if (values) return values
    const computed: Record<string, number | null> = {}
    PANEL_TEMPLATES.forEach((template) => {
      const series: ChartPoint[] = bars.map((bar, index, array) => ({
        time: bar.time,
        value: template.compute(bar, index, array),
      }))
      const point = nearestPoint(series, crosshairTime)
      computed[template.id] = point?.value ?? null
    })
    return computed
  }, [bars, crosshairTime, values])

  const metricPalette = useMemo(() => {
    const lookup: Record<string, string> = {}
    PANEL_TEMPLATES.forEach((template) => {
      lookup[template.id] = template.color
      lookup[template.label] = template.color
    })
    return lookup
  }, [])

  const metricReadouts = useMemo(() => {
    const formatValue = (value: number | null): string => {
      if (value == null || !Number.isFinite(value)) return '—'
      const abs = Math.abs(value)
      if (abs >= 1000) return value.toFixed(0)
      if (abs >= 100) return value.toFixed(1)
      if (abs >= 1) return value.toFixed(2)
      return value.toPrecision(3)
    }
    return RADAR_METRICS.map((metric) => {
      const raw = latestValues[metric] ?? null
      const numeric = typeof raw === 'number' && Number.isFinite(raw) ? raw : null
      return {
        metric,
        value: numeric,
        display: formatValue(numeric),
        color: metricPalette[metric] ?? '#94a3b8',
      }
    })
  }, [latestValues, metricPalette])

  const radarData = useMemo(() => {
    const maxValue =
      metricReadouts.reduce((max, item) => Math.max(max, Math.abs(item.value ?? 0)), 0) || 1
    return metricReadouts.map((item) => ({
      axis: item.metric,
      value: (Math.abs(item.value ?? 0) / maxValue) * 100,
    }))
  }, [metricReadouts])

  return (
    <div className={styles.radarCard} style={{ width, minWidth: width }}>
      <div className={styles.radarHeader}>
        <div>
          <h3 className={styles.radarTitle}>Options Radar</h3>
          <p className={styles.radarSubtitle}>Θ · Γ · ρ · Δ · IV · ν</p>
        </div>
      </div>
      <div className={styles.radarChart}>
        <ResponsiveContainer>
          <RadarChart data={radarData} outerRadius="80%">
            <PolarGrid stroke="rgba(148, 163, 184, 0.2)" />
            <PolarAngleAxis dataKey="axis" stroke="rgba(148, 163, 184, 0.8)" tick={{ fontSize: 12 }} />
            <Radar dataKey="value" stroke="#60a5fa" fill="#60a5fa" fillOpacity={0.25} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
      <div className={styles.radarMetrics}>
        {metricReadouts.map((item) => (
          <div key={item.metric} className={styles.radarMetric}>
            <span className={styles.radarMetricLabel} style={{ color: item.color }}>
              {item.metric}
            </span>
            <span className={styles.radarMetricValue}>{item.display}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default OptionsRadar
