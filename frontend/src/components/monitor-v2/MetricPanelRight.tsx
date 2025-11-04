import React from 'react'
import type { MetricPanelProps } from '../../types/monitor-v2'

export const MetricPanelRight: React.FC<MetricPanelProps> = ({
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
            {config.activeIndicator.toUpperCase()} Distribution
          </h4>
          <select
            value={config.activeIndicator}
            onChange={(e) => onConfigChange({ activeIndicator: e.target.value as any })}
            className="bg-gray-700 text-gray-200 rounded px-2 py-0.5 text-xs border-none"
          >
            <option value="iv">IV</option>
            <option value="delta">Delta</option>
            <option value="gamma">Gamma</option>
            <option value="theta">Theta</option>
            <option value="vega">Vega</option>
            <option value="oi">OI</option>
          </select>
        </div>
      </div>

      {/* Chart Area - Mock Stacked Bar Chart */}
      <div className="relative h-full bg-gradient-to-b from-gray-950 to-gray-900 p-3">
        {/* Y-Axis Price Labels (synced with main chart) */}
        <div className="absolute right-1 top-4 bottom-4 flex flex-col justify-between text-xs text-gray-500 font-mono">
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
              x1="0"
              y1={16 + (i * (100 / 5)) + '%'}
              x2="calc(100% - 45px)"
              y2={16 + (i * (100 / 5)) + '%'}
              stroke="#374151"
              strokeWidth="1"
            />
          ))}
        </svg>

        {/* Stacked Horizontal Bars (Call/Put distribution) */}
        <svg className="absolute left-2 top-6 right-11 bottom-6 w-full h-full">
          {[...Array(20)].map((_, i) => {
            const y = (i / 20) * 100
            const callWidth = 20 + Math.random() * 35
            const putWidth = 20 + Math.random() * 35
            const color = config.activeIndicator === 'iv' ? '#3b82f6' :
                         config.activeIndicator === 'delta' ? '#10b981' :
                         config.activeIndicator === 'gamma' ? '#f59e0b' :
                         config.activeIndicator === 'theta' ? '#ef4444' :
                         config.activeIndicator === 'vega' ? '#8b5cf6' : '#ec4899'

            return (
              <g key={i}>
                {/* Put Bar (left side) */}
                <rect
                  x={`${50 - putWidth}%`}
                  y={`${y}%`}
                  width={`${putWidth}%`}
                  height="3%"
                  fill={color}
                  opacity="0.5"
                  className="hover:opacity-90 transition-opacity cursor-pointer"
                />
                {/* Call Bar (right side) */}
                <rect
                  x="50%"
                  y={`${y}%`}
                  width={`${callWidth}%`}
                  height="3%"
                  fill={color}
                  opacity="0.8"
                  className="hover:opacity-100 transition-opacity cursor-pointer"
                />
                {/* Center Line */}
                <line
                  x1="50%"
                  y1={`${y}%`}
                  x2="50%"
                  y2={`${y + 3}%`}
                  stroke="#6b7280"
                  strokeWidth="1"
                  opacity="0.5"
                />
              </g>
            )
          })}
        </svg>

        {/* Legend */}
        <div className="absolute bottom-2 left-1/2 transform -translate-x-1/2 bg-gray-800/90 backdrop-blur px-3 py-1.5 rounded text-xs flex gap-3">
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded" style={{ opacity: 0.5, backgroundColor:
              config.activeIndicator === 'iv' ? '#3b82f6' :
              config.activeIndicator === 'delta' ? '#10b981' :
              config.activeIndicator === 'gamma' ? '#f59e0b' :
              config.activeIndicator === 'theta' ? '#ef4444' :
              config.activeIndicator === 'vega' ? '#8b5cf6' : '#ec4899'
            }} />
            <span className="text-gray-400 text-xs">Put</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded" style={{ opacity: 0.8, backgroundColor:
              config.activeIndicator === 'iv' ? '#3b82f6' :
              config.activeIndicator === 'delta' ? '#10b981' :
              config.activeIndicator === 'gamma' ? '#f59e0b' :
              config.activeIndicator === 'theta' ? '#ef4444' :
              config.activeIndicator === 'vega' ? '#8b5cf6' : '#ec4899'
            }} />
            <span className="text-gray-300 text-xs">Call</span>
          </div>
        </div>
      </div>
    </div>
  )
}
