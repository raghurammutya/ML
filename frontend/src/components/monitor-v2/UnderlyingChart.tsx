import React from 'react'
import type { UnderlyingChartProps } from '../../types/monitor-v2'

export const UnderlyingChart: React.FC<UnderlyingChartProps> = ({
  symbol,
  timeframe,
  config,
  onConfigChange,
  height,
  replayTime,
}) => {
  return (
    <div
      className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden"
      style={{ height }}
    >
      {/* Chart Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-700 bg-gray-800">
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-semibold text-white">{symbol}</h3>
          <span className="text-xs text-gray-400">{timeframe}</span>
          {replayTime && (
            <span className="text-xs text-purple-400">
              Replay: {new Date(replayTime).toLocaleString()}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => onConfigChange({ candleType: 'candle' })}
            className={`px-2 py-1 rounded text-xs ${
              config.candleType === 'candle'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-700 text-gray-400'
            }`}
            title="Candlestick"
          >
            📊
          </button>
          <button
            onClick={() => onConfigChange({ candleType: 'line' })}
            className={`px-2 py-1 rounded text-xs ${
              config.candleType === 'line'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-700 text-gray-400'
            }`}
            title="Line Chart"
          >
            📈
          </button>
          <button
            onClick={() => onConfigChange({ showVolume: !config.showVolume })}
            className={`px-2 py-1 rounded text-xs ${
              config.showVolume
                ? 'bg-blue-600 text-white'
                : 'bg-gray-700 text-gray-400'
            }`}
            title="Toggle Volume"
          >
            📊 Vol
          </button>
          <button
            onClick={() => onConfigChange({ showGrid: !config.showGrid })}
            className={`px-2 py-1 rounded text-xs ${
              config.showGrid
                ? 'bg-blue-600 text-white'
                : 'bg-gray-700 text-gray-400'
            }`}
            title="Toggle Grid"
          >
            #
          </button>
        </div>
      </div>

      {/* Chart Area - Mock Candlestick Chart */}
      <div className="relative h-full bg-gradient-to-b from-gray-950 to-gray-900 p-4">
        {/* Y-Axis Price Labels */}
        <div className="absolute left-2 top-12 bottom-4 flex flex-col justify-between text-xs text-gray-500 font-mono">
          <div>25,200</div>
          <div>25,000</div>
          <div>24,800</div>
          <div>24,600</div>
          <div>24,400</div>
        </div>

        {/* Grid Lines */}
        <svg className="absolute inset-0 w-full h-full pointer-events-none opacity-20">
          {[...Array(5)].map((_, i) => (
            <line
              key={`h-${i}`}
              x1="60"
              y1={40 + (i * (100 / 5)) + '%'}
              x2="100%"
              y2={40 + (i * (100 / 5)) + '%'}
              stroke="#374151"
              strokeWidth="1"
            />
          ))}
          {[...Array(12)].map((_, i) => (
            <line
              key={`v-${i}`}
              x1={60 + (i * (100 / 12)) + '%'}
              y1="40"
              x2={60 + (i * (100 / 12)) + '%'}
              y2="calc(100% - 30px)"
              stroke="#374151"
              strokeWidth="1"
            />
          ))}
        </svg>

        {/* Mock Candlesticks */}
        <svg className="absolute left-16 top-12 right-4 bottom-12 w-full h-full">
          {/* Generate mock candlestick data */}
          {[...Array(40)].map((_, i) => {
            const x = (i / 40) * 100
            const isGreen = Math.random() > 0.5
            const open = 45 + Math.random() * 30
            const close = open + (isGreen ? 1 : -1) * Math.random() * 15
            const high = Math.max(open, close) + Math.random() * 8
            const low = Math.min(open, close) - Math.random() * 8

            return (
              <g key={i}>
                {/* Wick */}
                <line
                  x1={`${x}%`}
                  y1={`${100 - high}%`}
                  x2={`${x}%`}
                  y2={`${100 - low}%`}
                  stroke={isGreen ? '#10b981' : '#ef4444'}
                  strokeWidth="1"
                  opacity="0.6"
                />
                {/* Body */}
                <rect
                  x={`${x - 0.8}%`}
                  y={`${100 - Math.max(open, close)}%`}
                  width="1.6%"
                  height={`${Math.abs(close - open)}%`}
                  fill={isGreen ? '#10b981' : '#ef4444'}
                  opacity="0.9"
                />
              </g>
            )
          })}
        </svg>

        {/* X-Axis Time Labels */}
        <div className="absolute bottom-2 left-16 right-4 flex justify-between text-xs text-gray-500 font-mono">
          <div>09:30</div>
          <div>11:00</div>
          <div>12:30</div>
          <div>14:00</div>
          <div>15:30</div>
        </div>

        {/* Current Price Indicator */}
        <div className="absolute right-4 top-1/2 transform -translate-y-1/2">
          <div className="bg-green-600 text-white px-2 py-1 rounded text-xs font-bold shadow-lg">
            24,850.25 ▲
          </div>
        </div>

        {/* Stats Overlay */}
        <div className="absolute top-2 left-16 flex gap-4 text-xs font-mono">
          <div className="bg-gray-800/80 backdrop-blur px-3 py-1 rounded">
            <span className="text-gray-400">O:</span>
            <span className="text-white ml-1">24,720</span>
          </div>
          <div className="bg-gray-800/80 backdrop-blur px-3 py-1 rounded">
            <span className="text-gray-400">H:</span>
            <span className="text-green-400 ml-1">25,180</span>
          </div>
          <div className="bg-gray-800/80 backdrop-blur px-3 py-1 rounded">
            <span className="text-gray-400">L:</span>
            <span className="text-red-400 ml-1">24,420</span>
          </div>
          <div className="bg-gray-800/80 backdrop-blur px-3 py-1 rounded">
            <span className="text-gray-400">C:</span>
            <span className="text-white ml-1">24,850</span>
          </div>
          <div className="bg-gray-800/80 backdrop-blur px-3 py-1 rounded">
            <span className="text-gray-400">Vol:</span>
            <span className="text-blue-400 ml-1">1.2M</span>
          </div>
        </div>
      </div>
    </div>
  )
}
