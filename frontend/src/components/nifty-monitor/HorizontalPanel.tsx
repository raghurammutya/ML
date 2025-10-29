import { useMemo } from 'react'
import { ResponsiveContainer, LineChart, Line, YAxis, XAxis, Tooltip, ReferenceLine } from 'recharts'
import type { FoIndicatorDefinition, FoMoneynessSeries } from '../../types'
import { useMonitorSync } from './MonitorSyncContext'

export interface HorizontalPanelProps {
  panel: FoIndicatorDefinition
  data: FoMoneynessSeries[]
  colorMap: Record<string, string>
  collapsed: boolean
  onToggleCollapse: () => void
}

interface CombinedRow {
  time: number
  label: string
  [expiry: string]: number | string
}

const normalizeEpochSeconds = (value: number): number => (value > 1e12 ? Math.floor(value / 1000) : value)

const formatTimeLabel = (raw: number) => {
  const ms = raw > 1e12 ? raw : raw * 1000
  return new Date(ms).toLocaleString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    day: '2-digit',
    month: 'short',
    hour12: false,
    timeZone: 'Asia/Kolkata',
  })
}

const combineSeries = (series: FoMoneynessSeries[]): CombinedRow[] => {
  const map: Record<number, { label: string; values: Record<string, number> }> = {}
  series
    .filter(s => s.bucket === 'ATM')
    .forEach(s => {
      const expiry = s.expiry
      s.points.forEach(pt => {
        const raw = typeof pt.time === 'number' ? pt.time : Date.parse(String(pt.time))
        if (Number.isNaN(raw)) return
        const normalized = normalizeEpochSeconds(raw)
        if (!map[normalized]) {
          map[normalized] = { label: formatTimeLabel(raw), values: {} }
        }
        map[normalized].values[expiry] = pt.value
      })
    })
  return Object.entries(map)
    .map(([timeStr, entry]) => ({
      time: Number(timeStr),
      label: entry.label,
      ...entry.values,
    }))
    .sort((a, b) => a.time - b.time)
}

const TooltipContent = ({ active, payload }: any) => {
  if (!active || !payload || !payload.length) return null
  const point = payload[0].payload
  return (
    <div className="monitor-tooltip">
      <div className="monitor-tooltip__title">{point.label}</div>
      {payload.map((line: any) => (
        <div key={line.dataKey} className="monitor-tooltip__row">
          <span style={{ color: line.color }}>{line.name}</span>
          <span>{line.value?.toFixed(3)}</span>
        </div>
      ))}
    </div>
  )
}

const HorizontalPanel = ({ panel, data, colorMap, collapsed, onToggleCollapse }: HorizontalPanelProps) => {
  const combined = useMemo(() => combineSeries(data), [data])
  const { crosshairTime, timeRange } = useMonitorSync()
  const filtered = useMemo(() => {
    if (!timeRange) return combined
    const windowed = combined.filter(point => point.time >= timeRange.from && point.time <= timeRange.to)
    return windowed.length ? windowed : combined
  }, [combined, timeRange])
  const crosshairX = typeof crosshairTime === 'number' ? crosshairTime : undefined

  return (
    <div className="monitor-card">
      <div className="monitor-card__header">
        <div>
          <strong>{panel.label}</strong>
          <span className="monitor-card__subtext"> {panel.option_side === 'both' ? 'Calls & Puts' : panel.option_side}</span>
        </div>
        <button className="monitor-card__btn" onClick={onToggleCollapse}>
          {collapsed ? 'Expand' : 'Collapse'}
        </button>
      </div>
      {!collapsed && (
        <div style={{ width: '100%', height: 180 }}>
          <ResponsiveContainer>
            <LineChart data={filtered} margin={{ top: 6, right: 8, bottom: 2, left: 0 }}>
              <XAxis
                dataKey="time"
                type="number"
                domain={[
                  timeRange ? timeRange.from : 'auto',
                  timeRange ? timeRange.to : 'auto',
                ]}
                hide
              />
              <YAxis stroke="#555" width={48} />
              <Tooltip content={<TooltipContent />} wrapperStyle={{ background: '#0f172a', border: '1px solid #1d2535' }} />
              {typeof crosshairX === 'number' && (
                <ReferenceLine x={crosshairX} stroke="#26a69a" strokeDasharray="4 4" />
              )}
              {Object.keys(colorMap).map((expiry) => (
                <Line
                  key={expiry}
                  type="monotone"
                  dataKey={expiry}
                  dot={false}
                  stroke={colorMap[expiry]}
                  strokeWidth={2}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

export default HorizontalPanel
