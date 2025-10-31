import { useMemo, useCallback, useState, useEffect } from 'react'
import { ResponsiveContainer, LineChart, Line, YAxis, XAxis, Tooltip, ReferenceLine } from 'recharts'
import type { FoIndicatorDefinition, FoMoneynessSeries } from '../../types'
import { useMonitorSync } from './MonitorSyncContext'

export interface HorizontalPanelProps {
  panel: FoIndicatorDefinition
  data: FoMoneynessSeries[]
  colorMap: Record<string, string>
  collapsed: boolean
  onToggleCollapse: () => void
  onShowChart?: (context: { bucket: string; expiry: string; timestamp: number; underlying: string }) => void
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

const HorizontalPanel = ({ panel, data, colorMap, collapsed, onToggleCollapse, onShowChart }: HorizontalPanelProps) => {
  const combined = useMemo(() => combineSeries(data), [data])
  const { crosshairTime, timeRange } = useMonitorSync()
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; timestamp: number } | null>(null)

  const filtered = useMemo(() => {
    if (!timeRange) return combined
    const windowed = combined.filter(point => point.time >= timeRange.from && point.time <= timeRange.to)
    return windowed.length ? windowed : combined
  }, [combined, timeRange])
  const crosshairX = typeof crosshairTime === 'number' ? crosshairTime : undefined

  const handleContextMenu = useCallback((event: React.MouseEvent) => {
    event.preventDefault()

    // Use crosshairTime if available, otherwise use current time
    const timestamp = crosshairTime || Math.floor(Date.now() / 1000)

    setContextMenu({
      x: event.clientX,
      y: event.clientY,
      timestamp: timestamp
    })
  }, [crosshairTime])

  const handleShowChart = useCallback(() => {
    if (!onShowChart || !contextMenu) return

    const firstExpiry = Object.keys(colorMap)[0]
    if (!firstExpiry) return

    onShowChart({
      bucket: 'ATM',
      expiry: firstExpiry,
      timestamp: contextMenu.timestamp,
      underlying: 'NIFTY'
    })
    setContextMenu(null)
  }, [onShowChart, contextMenu, colorMap])

  useEffect(() => {
    if (!contextMenu) return
    const handleClick = () => setContextMenu(null)
    const handleEscape = (e: KeyboardEvent) => e.key === 'Escape' && setContextMenu(null)
    window.addEventListener('click', handleClick)
    window.addEventListener('keydown', handleEscape)
    return () => {
      window.removeEventListener('click', handleClick)
      window.removeEventListener('keydown', handleEscape)
    }
  }, [contextMenu])

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
        <div style={{ width: '100%', height: 180 }} onContextMenu={handleContextMenu}>
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

      {/* Context Menu */}
      {contextMenu && (
        <div
          style={{
            position: 'fixed',
            left: contextMenu.x,
            top: contextMenu.y,
            backgroundColor: '#1e222d',
            border: '1px solid #2f3b52',
            borderRadius: '6px',
            padding: '4px 0',
            boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
            zIndex: 9999,
            minWidth: '180px'
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <div
            style={{
              padding: '8px 12px',
              cursor: 'pointer',
              borderRadius: '4px',
              transition: 'background-color 0.15s',
              color: '#d1d4dc'
            }}
            onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#2f3b52'}
            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
            onClick={() => { console.log('Copy value'); setContextMenu(null) }}
          >
            📋 Copy value
          </div>
          <div
            style={{
              padding: '8px 12px',
              cursor: 'pointer',
              borderRadius: '4px',
              transition: 'background-color 0.15s',
              color: '#d1d4dc'
            }}
            onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#2f3b52'}
            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
            onClick={() => { console.log('Add Alert'); setContextMenu(null) }}
          >
            🔔 Add Alert
          </div>
          <div
            style={{
              padding: '8px 12px',
              cursor: 'pointer',
              borderRadius: '4px',
              transition: 'background-color 0.15s',
              color: '#d1d4dc'
            }}
            onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#2f3b52'}
            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
            onClick={() => { console.log('Settings'); setContextMenu(null) }}
          >
            ⚙️ Settings
          </div>
          <hr style={{ borderColor: '#2f3b52', margin: '6px 0' }} />
          <div
            style={{
              padding: '8px 12px',
              cursor: 'pointer',
              borderRadius: '4px',
              transition: 'background-color 0.15s',
              color: '#d1d4dc'
            }}
            onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#2f3b52'}
            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
            onClick={handleShowChart}
          >
            📊 Show Chart
          </div>
        </div>
      )}
    </div>
  )
}

export default HorizontalPanel
