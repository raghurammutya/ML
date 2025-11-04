import React from 'react'
import type { MetricPanelProps } from '../../types/monitor-v2'

export const MetricPanelLeft: React.FC<MetricPanelProps> = ({
  config,
  onConfigChange,
  height,
}) => {
  return (
    <div
      className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden"
      style={{ height }}
    >
      {/* Panel Header */}
      <div className="px-3 py-2 border-b border-gray-700 bg-gray-800">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold text-white uppercase">
            {config.activeIndicator.toUpperCase()} by Strike
          </h4>
          <button
            onClick={() => onConfigChange({ showLegend: !config.showLegend })}
            className="text-xs text-gray-400 hover:text-gray-200"
            title="Toggle Legend"
          >
            {config.showLegend ? '👁' : '👁‍🗨'}
          </button>
        </div>
      </div>

      {/* Chart Area - Mock Horizontal Bar Chart */}
      <div className="relative h-full bg-gradient-to-b from-gray-950 to-gray-900 p-3">
        {/* Y-Axis Price Labels (synced with main chart) */}
        <div className="absolute left-1 top-4 bottom-4 flex flex-col justify-between text-xs text-gray-500 font-mono">
          <div>25,200</div>
          <div>25,000</div>
          <div>24,800</div>
          <div>24,600</div>
          <div>24,400</div>
        </div>

        {/* Grid Lines */}
        <svg className="absolute inset-0 w-full h-full pointer-events-none opacity-10">
          {[...Array(5)].map((_, i) => (
            <line
              key={`h-${i}`}
              x1="45"
              y1={16 + (i * (100 / 5)) + '%'}
              x2="100%"
              y2={16 + (i * (100 / 5)) + '%'}
              stroke="#374151"
              strokeWidth="1"
            />
          ))}
        </svg>

        {/* Horizontal Bars (IV/Delta/Gamma by Strike Price) */}
        <svg className="absolute left-11 top-6 right-2 bottom-6 w-full h-full">
          {[...Array(20)].map((_, i) => {
            const y = (i / 20) * 100
            const barWidth = 30 + Math.random() * 65
            const color = config.activeIndicator === 'iv' ? '#3b82f6' :
                         config.activeIndicator === 'delta' ? '#10b981' :
                         config.activeIndicator === 'gamma' ? '#f59e0b' :
                         config.activeIndicator === 'theta' ? '#ef4444' :
                         config.activeIndicator === 'vega' ? '#8b5cf6' : '#ec4899'

            return (
              <g key={i}>
                {/* Bar */}
                <rect
                  x="0"
                  y={`${y}%`}
                  width={`${barWidth}%`}
                  height="3%"
                  fill={color}
                  opacity="0.7"
                  className="hover:opacity-100 transition-opacity cursor-pointer"
                />
                {/* Value Label */}
                <text
                  x={`${barWidth + 2}%`}
                  y={`${y + 2}%`}
                  fill="#9ca3af"
                  fontSize="8"
                  fontFamily="monospace"
                >
                  {(Math.random() * 100).toFixed(1)}
                </text>
              </g>
            )
          })}
        </svg>

        {/* Legend */}
        {config.showLegend && (
          <div className="absolute bottom-2 right-2 bg-gray-800/90 backdrop-blur px-2 py-1.5 rounded text-xs">
            <div className="flex items-center gap-2">
              <div className="w-2.5 h-2.5 rounded" style={{
                backgroundColor: config.activeIndicator === 'iv' ? '#3b82f6' :
                                config.activeIndicator === 'delta' ? '#10b981' :
                                config.activeIndicator === 'gamma' ? '#f59e0b' :
                                config.activeIndicator === 'theta' ? '#ef4444' :
                                config.activeIndicator === 'vega' ? '#8b5cf6' : '#ec4899'
              }} />
              <span className="text-gray-300 text-xs">{config.activeIndicator.toUpperCase()}</span>
            </div>
            <div className="text-gray-500 text-xs mt-0.5">Synced Y-axis</div>
          </div>
        )}
      </div>
    </div>
  )
}
