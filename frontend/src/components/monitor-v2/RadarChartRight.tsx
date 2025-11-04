import React from 'react'
import type { RadarChartProps } from '../../types/monitor-v2'

export const RadarChartRight: React.FC<RadarChartProps> = ({ data, height }) => {
  return (
    <div
      className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden"
      style={{ height }}
    >
      {/* Header */}
      <div className="px-3 py-2 border-b border-gray-700 bg-gray-800">
        <h4 className="text-xs font-semibold text-white uppercase">Greeks Radar</h4>
      </div>

      {/* Radar Chart - Placeholder */}
      <div className="flex items-center justify-center h-full bg-gray-950">
        <div className="text-center text-gray-500">
          <div className="text-2xl mb-2">🎯</div>
          <div className="text-xs">Greeks Radar</div>
          <div className="text-xs text-gray-600 mt-1">{data.length} metrics</div>
          <div className="text-xs text-gray-600 mt-2">
            Greeks distribution
          </div>
        </div>
      </div>
    </div>
  )
}
