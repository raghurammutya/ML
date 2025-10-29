import { useMemo } from 'react'
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
}

const TooltipContent = ({ active, payload }: any) => {
  if (!active || !payload || !payload.length) return null
  const datum = payload[0].payload
  return (
    <div className="monitor-tooltip">
      <div className="monitor-tooltip__row">
        <span>Strike</span>
        <span>{datum.strike}</span>
      </div>
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
      {typeof datum.call_oi === 'number' && (
        <div className="monitor-tooltip__row">
          <span>Call OI</span>
          <span>{datum.call_oi.toLocaleString('en-IN')}</span>
        </div>
      )}
      {typeof datum.put_oi === 'number' && (
        <div className="monitor-tooltip__row">
          <span>Put OI</span>
          <span>{datum.put_oi.toLocaleString('en-IN')}</span>
        </div>
      )}
      {datum.expiry && (
        <div className="monitor-tooltip__row">
          <span>Expiry</span>
          <span>{datum.expiry}</span>
        </div>
      )}
    </div>
  )
}

const VerticalPanel = ({ panel, data, colorMap, collapsed, onToggleCollapse, height }: VerticalPanelProps) => {
  const { priceRange } = useMonitorSync()
  const scatterSeries = useMemo(() => data.map(series => ({
    expiry: series.expiry,
    points: series.points.map(pt => ({ ...pt, expiry: series.expiry })),
  })), [data])

  return (
    <div className="vertical-panel" style={{ height }}>
      <div className="vertical-panel__header">
        <span>{panel.label}</span>
        <button onClick={onToggleCollapse}>{collapsed ? '+' : '−'}</button>
      </div>
      {!collapsed && (
        <div className="vertical-panel__chart">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart layout="vertical" margin={{ top: 12, right: 4, bottom: 12, left: 4 }}>
              <YAxis
                type="number"
                dataKey="strike"
                stroke="#2f3b52"
                tick={{ fill: '#64748b', fontSize: 10 }}
                domain={priceRange ? [priceRange.min, priceRange.max] : ['auto', 'auto']}
                width={0}
                tickLine={false}
                axisLine={false}
              />
              <XAxis type="number" dataKey="value" hide domain={['auto', 'auto']} />
              <Tooltip content={<TooltipContent />} cursor={{ stroke: '#26a69a', strokeDasharray: '3 3' }} />
              {scatterSeries.map(series => (
                <Scatter
                  key={series.expiry}
                  name={series.expiry}
                  data={series.points}
                  line
                  lineJointType="monotoneX"
                  lineType="fitting"
                  fill={colorMap[series.expiry] || '#fff'}
                  stroke={colorMap[series.expiry] || '#fff'}
                  strokeWidth={1.5}
                />
              ))}
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

export default VerticalPanel
