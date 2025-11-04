import React from 'react'
import type { IndicatorType } from '../../types/monitor-v2'

interface MetricIndicator {
  type: IndicatorType
  label: string
  color: string
  value?: number
}

interface VerticalMetricIndicatorsProps {
  height?: number
  activeIndicator?: IndicatorType
  onIndicatorClick?: (indicator: IndicatorType) => void
}

const METRIC_INDICATORS: MetricIndicator[] = [
  { type: 'theta', label: 'Theta', color: '#f97316' },
  { type: 'oi', label: 'OI', color: '#059669' },
  { type: 'iv', label: 'IV', color: '#3b82f6' },
  { type: 'volume', label: 'Fut OI', color: '#a855f7' },
  { type: 'pcr', label: 'PCR', color: '#22c55e' },
  { type: 'gamma', label: 'Gamma', color: '#fb923c' },
  { type: 'delta', label: 'Delta', color: '#047857' },
]

export const VerticalMetricIndicators: React.FC<VerticalMetricIndicatorsProps> = ({
  height = 500,
  activeIndicator,
  onIndicatorClick,
}) => {
  const containerStyle: React.CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
    height,
    justifyContent: 'center',
    padding: '20px 0',
  }

  const indicatorButtonStyle = (color: string, isActive: boolean): React.CSSProperties => ({
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '12px 16px',
    backgroundColor: color,
    color: '#ffffff',
    fontSize: '11px',
    fontWeight: 700,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    borderRadius: '6px',
    border: isActive ? '2px solid #ffffff' : 'none',
    cursor: 'pointer',
    transition: 'all 0.2s',
    minWidth: '90px',
    boxShadow: isActive
      ? '0 0 0 3px rgba(255, 255, 255, 0.3)'
      : '0 2px 4px rgba(0, 0, 0, 0.3)',
    position: 'relative',
  })

  return (
    <div style={containerStyle}>
      {METRIC_INDICATORS.map((indicator) => {
        const isActive = activeIndicator === indicator.type
        return (
          <button
            key={indicator.type}
            style={indicatorButtonStyle(indicator.color, isActive)}
            onClick={() => onIndicatorClick?.(indicator.type)}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = 'scale(1.05)'
              e.currentTarget.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.4)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'scale(1)'
              e.currentTarget.style.boxShadow = isActive
                ? '0 0 0 3px rgba(255, 255, 255, 0.3)'
                : '0 2px 4px rgba(0, 0, 0, 0.3)'
            }}
          >
            {indicator.label}
          </button>
        )
      })}
    </div>
  )
}
