import React from 'react'
import type {
  UniverseLayout,
  UniverseFilters,
  ChartConfig,
} from '../../types/monitor-v2'
import { UnderlyingChart } from './UnderlyingChart'
import { MetricChartPanel } from './MetricChartPanel'

interface UniversePageProps {
  layout: UniverseLayout
  filters: UniverseFilters
  chartConfig: ChartConfig
  onChartConfigChange: (config: Partial<ChartConfig>) => void
  replayTime?: number
}

export const UniversePage: React.FC<UniversePageProps> = ({
  layout,
  chartConfig,
  onChartConfigChange,
  replayTime,
}) => {
  // Metric configurations for side panels (Y-axis synced)
  const sidePanelMetrics = [
    { type: 'theta' as const, label: 'Theta', color: '#f97316' },
    { type: 'oi' as const, label: 'OI', color: '#059669' },
    { type: 'iv' as const, label: 'IV', color: '#3b82f6' },
    { type: 'volume' as const, label: 'Fut OI', color: '#a855f7' },
    { type: 'pcr' as const, label: 'PCR', color: '#22c55e' },
    { type: 'gamma' as const, label: 'Gamma', color: '#fb923c' },
    { type: 'delta' as const, label: 'Delta', color: '#047857' },
  ]

  // Metric configurations for bottom panels (X-axis synced)
  const bottomPanelMetrics = [
    { type: 'theta' as const, label: 'Theta', color: '#ef4444' },
    { type: 'delta' as const, label: 'Delta', color: '#10b981' },
    { type: 'gamma' as const, label: 'Gamma', color: '#f59e0b' },
    { type: 'vega' as const, label: 'Vega', color: '#8b5cf6' },
    { type: 'iv' as const, label: 'IV', color: '#3b82f6' },
    { type: 'volume' as const, label: 'Max Pain', color: '#f97316' },
    { type: 'pcr' as const, label: 'PCR', color: '#22c55e' },
    { type: 'oi' as const, label: 'OI', color: '#ec4899' },
  ]

  const chartHeight = layout.chartHeight || 600
  const sidePanelWidth = 250
  const sidePanelChartHeight = 150
  const bottomPanelHeight = 200

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', backgroundColor: '#030712', overflow: 'hidden' }}>
      {/* Main 3-Column Layout */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'row', gap: '12px', padding: '12px', overflow: 'hidden' }}>
        {/* Left Column - Y-Axis Synced Metric Charts */}
        <div
          style={{
            width: sidePanelWidth,
            flexShrink: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
            overflowY: 'auto',
            overflowX: 'hidden',
          }}
        >
          {sidePanelMetrics.map((metric) => (
            <MetricChartPanel
              key={`left-${metric.type}`}
              metric={metric.type}
              label={metric.label}
              color={metric.color}
              height={sidePanelChartHeight}
              orientation="vertical"
              syncAxis="y"
            />
          ))}
        </div>

        {/* Center Column - Main Chart */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
          <UnderlyingChart
            symbol={chartConfig.symbol}
            timeframe={chartConfig.timeframe}
            config={chartConfig}
            onConfigChange={onChartConfigChange}
            height={chartHeight}
            replayTime={replayTime}
          />
        </div>

        {/* Right Column - Y-Axis Synced Metric Charts */}
        <div
          style={{
            width: sidePanelWidth,
            flexShrink: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
            overflowY: 'auto',
            overflowX: 'hidden',
          }}
        >
          {sidePanelMetrics.map((metric) => (
            <MetricChartPanel
              key={`right-${metric.type}`}
              metric={metric.type}
              label={metric.label}
              color={metric.color}
              height={sidePanelChartHeight}
              orientation="vertical"
              syncAxis="y"
            />
          ))}
        </div>
      </div>

      {/* Bottom Row - X-Axis Synced Metric Charts (Horizontal Scroll) */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'row',
          gap: '12px',
          padding: '0 12px 12px 12px',
          overflowX: 'auto',
          overflowY: 'hidden',
          borderTop: '1px solid #374151',
          height: bottomPanelHeight + 24,
          flexShrink: 0,
        }}
      >
        {bottomPanelMetrics.map((metric) => (
          <MetricChartPanel
            key={`bottom-${metric.type}`}
            metric={metric.type}
            label={metric.label}
            color={metric.color}
            width={300}
            height={bottomPanelHeight}
            orientation="horizontal"
            syncAxis="x"
          />
        ))}
      </div>
    </div>
  )
}
