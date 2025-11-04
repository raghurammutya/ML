import React from 'react'
import type { IndicatorType } from '../../types/monitor-v2'

interface MetricChartPanelProps {
  metric: IndicatorType
  label: string
  color: string
  width?: number
  height?: number
  orientation: 'vertical' | 'horizontal'
  syncAxis?: 'x' | 'y' | 'none'
}

export const MetricChartPanel: React.FC<MetricChartPanelProps> = ({
  metric,
  label,
  color,
  width,
  height = 200,
  orientation,
}) => {
  const containerStyle: React.CSSProperties = {
    width: width || (orientation === 'horizontal' ? 300 : '100%'),
    height,
    backgroundColor: '#111827',
    border: '1px solid #374151',
    borderRadius: '8px',
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column',
    flexShrink: 0,
  }

  const headerStyle: React.CSSProperties = {
    backgroundColor: color,
    color: '#ffffff',
    padding: '8px 16px',
    fontSize: '12px',
    fontWeight: 700,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  }

  const chartAreaStyle: React.CSSProperties = {
    flex: 1,
    backgroundColor: '#0f1419',
    position: 'relative',
    padding: '12px',
  }

  // Mock chart data visualization
  const generateMockPath = () => {
    const points = Array.from({ length: 30 }, (_, i) => {
      const x = (i / 29) * 100
      const y = 30 + Math.sin(i * 0.4) * 20 + Math.random() * 10
      return `${x},${y}`
    })
    return `M ${points.map((p, i) => (i === 0 ? p : `L ${p}`)).join(' ')}`
  }

  return (
    <div style={containerStyle}>
      {/* Colored Header */}
      <div style={headerStyle}>
        <span>{label}</span>
        <span style={{ fontSize: '10px', opacity: 0.8 }}>●</span>
      </div>

      {/* Chart Area */}
      <div style={chartAreaStyle}>
        {/* Y-axis labels */}
        <div
          style={{
            position: 'absolute',
            left: '4px',
            top: '12px',
            bottom: '12px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            fontSize: '9px',
            color: '#6b7280',
            fontFamily: 'monospace',
          }}
        >
          <div>100</div>
          <div>75</div>
          <div>50</div>
          <div>25</div>
          <div>0</div>
        </div>

        {/* Chart SVG */}
        <svg
          style={{
            width: '100%',
            height: '100%',
            marginLeft: '24px',
          }}
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
        >
          {/* Grid lines */}
          <defs>
            <pattern id={`grid-${metric}`} width="10" height="20" patternUnits="userSpaceOnUse">
              <path d="M 10 0 L 0 0 0 20" fill="none" stroke="#1f2937" strokeWidth="0.5" />
            </pattern>
          </defs>
          <rect width="100" height="100" fill={`url(#grid-${metric})`} />

          {/* Area fill */}
          <path
            d={`${generateMockPath()} L 100,100 L 0,100 Z`}
            fill={color}
            opacity="0.2"
          />

          {/* Line */}
          <path
            d={generateMockPath()}
            fill="none"
            stroke={color}
            strokeWidth="2"
          />
        </svg>

        {/* X-axis labels (for horizontal orientation) */}
        {orientation === 'horizontal' && (
          <div
            style={{
              position: 'absolute',
              bottom: '4px',
              left: '24px',
              right: '4px',
              display: 'flex',
              justifyContent: 'space-between',
              fontSize: '8px',
              color: '#6b7280',
              fontFamily: 'monospace',
            }}
          >
            <span>09:30</span>
            <span>12:00</span>
            <span>15:30</span>
          </div>
        )}
      </div>
    </div>
  )
}
