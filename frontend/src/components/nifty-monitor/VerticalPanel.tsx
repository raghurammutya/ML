import { useMemo, useCallback, useState, useEffect } from 'react'
import { ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis, Tooltip } from 'recharts'
import type { FoIndicatorDefinition, FoStrikeSeries } from '../../types'
import { useMonitorSync } from './MonitorSyncContext'

export interface VerticalPanelProps {
  panel: FoIndicatorDefinition
  data: FoStrikeSeries[]
  colorMap: Record<string, string>
  collapsed: boolean
  onToggleCollapse: () => void
  height: number
  onShowChart?: (context: { strike: number; expiry: string; timestamp: number; underlying: string }) => void
}

const TooltipContent = ({ active, payload }: any) => {
  if (!active || !payload || !payload.length) return null
  const datum = payload[0].payload
  const seriesName = payload[0].name || ''
  const isSplit = seriesName.includes('CALL') || seriesName.includes('PUT')

  return (
    <div className="monitor-tooltip">
      <div className="monitor-tooltip__row">
        <span>Strike</span>
        <span>{datum.strike}</span>
      </div>
      {datum.expiry && (
        <div className="monitor-tooltip__row">
          <span>Expiry</span>
          <span>{datum.expiry}</span>
        </div>
      )}
      {isSplit ? (
        <div className="monitor-tooltip__row">
          <span>{seriesName.includes('CALL') ? 'Call IV' : 'Put IV'}</span>
          <span>{datum.value?.toFixed(4)}</span>
        </div>
      ) : (
        <>
          <div className="monitor-tooltip__row">
            <span>Value</span>
            <span>{datum.value?.toFixed(4)}</span>
          </div>
          {typeof datum.call === 'number' && (
            <div className="monitor-tooltip__row">
              <span>Call</span>
              <span>{datum.call.toFixed(4)}</span>
            </div>
          )}
          {typeof datum.put === 'number' && (
            <div className="monitor-tooltip__row">
              <span>Put</span>
              <span>{datum.put.toFixed(4)}</span>
            </div>
          )}
        </>
      )}
      {typeof datum.call_oi === 'number' && datum.call_oi > 0 && (
        <div className="monitor-tooltip__row">
          <span>Call OI</span>
          <span>{datum.call_oi.toLocaleString('en-IN')}</span>
        </div>
      )}
      {typeof datum.put_oi === 'number' && datum.put_oi > 0 && (
        <div className="monitor-tooltip__row">
          <span>Put OI</span>
          <span>{datum.put_oi.toLocaleString('en-IN')}</span>
        </div>
      )}
    </div>
  )
}

const VerticalPanel = ({ panel, data, colorMap, collapsed, onToggleCollapse, height, onShowChart }: VerticalPanelProps) => {
  const { priceRange } = useMonitorSync()
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; strike: number; expiry: string; timestamp: number } | null>(null)

  // For indicators like IV, create separate series for CALL and PUT
  // For others, use the combined value
  const scatterSeries = useMemo(() => {
    console.log(`[VerticalPanel ${panel.id}] Incoming data:`, data.length, 'series')
    if (data.length > 0) {
      const samplePoints = data[0].points ?? []
      console.log(`[VerticalPanel ${panel.id}] First series:`, data[0].expiry, 'with', samplePoints.length, 'points')
      if (samplePoints.length > 0) {
        console.log(`[VerticalPanel ${panel.id}] Sample point:`, samplePoints[0])
      }
    }

    const firstPoints = data[0]?.points ?? []
    const hasCallPut =
      firstPoints.length > 0 &&
      typeof firstPoints[0].call === 'number' &&
      typeof firstPoints[0].put === 'number'

    console.log(`[VerticalPanel ${panel.id}] hasCallPut=${hasCallPut}, indicator=${panel.indicator}`)

    if (hasCallPut && panel.indicator === 'iv') {
      // Create separate series for calls and puts
      const callSeries = data.map(series => ({
        expiry: series.expiry,
        side: 'call' as const,
        points: (series.points ?? [])
          .filter(pt => typeof pt.call === 'number')
          .map(pt => ({ ...pt, value: pt.call, expiry: series.expiry, side: 'call' })),
      }))
      const putSeries = data.map(series => ({
        expiry: series.expiry,
        side: 'put' as const,
        points: (series.points ?? [])
          .filter(pt => typeof pt.put === 'number')
          .map(pt => ({ ...pt, value: pt.put, expiry: series.expiry, side: 'put' })),
      }))
      const combined = [...callSeries, ...putSeries]
      console.log(`[VerticalPanel ${panel.id}] Created ${combined.length} series (${callSeries.length} call + ${putSeries.length} put)`)
      return combined
    }

    // Default: use combined value
    const defaultSeries = data.map(series => {
      const points = (series.points ?? []).map(pt => ({ ...pt, expiry: series.expiry }))
      return {
        expiry: series.expiry,
        side: undefined,
        points,
      }
    })
    console.log(`[VerticalPanel ${panel.id}] Using default series:`, defaultSeries.length)
    return defaultSeries
  }, [data, panel.indicator, panel.id])

  const handleContextMenu = useCallback((event: React.MouseEvent) => {
    event.preventDefault()
    if (!data.length) return

    const firstSeries = data[0]
    const firstPoints = firstSeries.points ?? []
    if (!firstPoints.length) return

    const atmStrike =
      firstPoints.find(p => p.underlying && Math.abs(p.strike - p.underlying) < 100)?.strike ?? firstPoints[0].strike

    setContextMenu({
      x: event.clientX,
      y: event.clientY,
      strike: atmStrike,
      expiry: firstSeries.expiry,
      timestamp: firstSeries.bucket_time || Date.now() / 1000
    })
  }, [data])

  const handleShowChart = useCallback(() => {
    if (!onShowChart || !contextMenu) return

    onShowChart({
      strike: contextMenu.strike,
      expiry: contextMenu.expiry,
      timestamp: contextMenu.timestamp,
      underlying: 'NIFTY'
    })
    setContextMenu(null)
  }, [onShowChart, contextMenu])

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
    <div className="vertical-panel" style={{ height }}>
      <div className="vertical-panel__header">
        <span>{panel.label}</span>
        <button onClick={onToggleCollapse}>{collapsed ? '+' : '−'}</button>
      </div>
      {!collapsed && (
        <div className="vertical-panel__chart" onContextMenu={handleContextMenu}>
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart layout="vertical" margin={{ top: 12, right: 4, bottom: 12, left: 4 }}>
              <YAxis
                type="number"
                dataKey="strike"
                stroke="#2f3b52"
                tick={{ fill: '#64748b', fontSize: 10 }}
                domain={priceRange ? [priceRange.min, priceRange.max] : ['auto', 'auto']}
                width={50}
                tickLine={true}
                axisLine={true}
              />
              <XAxis type="number" dataKey="value" hide domain={['auto', 'auto']} />
              <Tooltip content={<TooltipContent />} cursor={{ stroke: '#26a69a', strokeDasharray: '3 3' }} />
              {scatterSeries.map((series) => {
                const baseColor = colorMap[series.expiry] || '#fff'
                // For call/put series, use dashed line for puts
                const isDashed = series.side === 'put'
                const key = series.side ? `${series.expiry}-${series.side}` : series.expiry
                return (
                  <Scatter
                    key={key}
                    name={series.side ? `${series.expiry} (${series.side.toUpperCase()})` : series.expiry}
                    data={series.points}
                    line
                    lineJointType="monotoneX"
                    lineType="fitting"
                    fill={baseColor}
                    stroke={baseColor}
                    strokeWidth={1.5}
                    strokeDasharray={isDashed ? '5 5' : undefined}
                  />
                )
              })}
            </ScatterChart>
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

export default VerticalPanel
