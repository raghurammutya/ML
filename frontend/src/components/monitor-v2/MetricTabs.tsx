import React from 'react'
import type { MetricTabsProps } from '../../types/monitor-v2'

export const MetricTabs: React.FC<MetricTabsProps> = ({
  tabs,
  activeTabId,
  onTabChange,
  height,
  expiries,
}) => {
  const activeTab = tabs.find((t) => t.id === activeTabId)

  return (
    <div
      className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden"
      style={{ height }}
    >
      {/* Tab Headers - Large Colored Blocks */}
      <div className="flex items-center border-b border-gray-700 bg-gray-950 px-8 py-4 gap-2 overflow-x-auto">
        {tabs
          .filter((tab) => tab.isActive)
          .sort((a, b) => a.order - b.order)
          .map((tab) => {
            const isActive = activeTabId === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => onTabChange(tab.id)}
                style={{
                  padding: '14px 22px',
                  fontSize: '12px',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  color: '#ffffff',
                  backgroundColor: tab.color,
                  border: isActive ? '3px solid #ffffff' : 'none',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  whiteSpace: 'nowrap',
                  minWidth: '90px',
                  boxShadow: isActive
                    ? '0 4px 12px rgba(0, 0, 0, 0.5), 0 0 0 3px rgba(255, 255, 255, 0.2)'
                    : '0 2px 6px rgba(0, 0, 0, 0.3)',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = 'translateY(-2px)'
                  e.currentTarget.style.boxShadow = '0 6px 16px rgba(0, 0, 0, 0.6)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = 'translateY(0)'
                  e.currentTarget.style.boxShadow = isActive
                    ? '0 4px 12px rgba(0, 0, 0, 0.5), 0 0 0 3px rgba(255, 255, 255, 0.2)'
                    : '0 2px 6px rgba(0, 0, 0, 0.3)'
                }}
              >
                {tab.label}
              </button>
            )
          })}
      </div>

      {/* Tab Content - Mock Area Chart */}
      <div className="relative h-full bg-gradient-to-b from-gray-950 to-gray-900 p-4">
        {/* Y-Axis Value Labels */}
        <div className="absolute left-2 top-8 bottom-8 flex flex-col justify-between text-xs text-gray-500 font-mono">
          <div>100</div>
          <div>75</div>
          <div>50</div>
          <div>25</div>
          <div>0</div>
        </div>

        {/* Grid Lines */}
        <svg className="absolute inset-0 w-full h-full pointer-events-none opacity-10">
          {[...Array(5)].map((_, i) => (
            <line
              key={`h-${i}`}
              x1="50"
              y1={32 + (i * (100 / 5.5)) + '%'}
              x2="calc(100% - 20px)"
              y2={32 + (i * (100 / 5.5)) + '%'}
              stroke="#374151"
              strokeWidth="1"
            />
          ))}
          {[...Array(12)].map((_, i) => (
            <line
              key={`v-${i}`}
              x1={50 + (i * ((100 - 70) / 12)) + '%'}
              y1="32"
              x2={50 + (i * ((100 - 70) / 12)) + '%'}
              y2="calc(100% - 60px)"
              stroke="#374151"
              strokeWidth="1"
            />
          ))}
        </svg>

        {/* Mock Area Charts for each expiry */}
        <svg className="absolute left-12 top-8 right-5 bottom-16 w-full h-full">
          {expiries.slice(0, 3).map((expiry, expiryIdx) => {
            const color = activeTab?.color || '#3b82f6'
            const opacity = 0.8 - (expiryIdx * 0.2)

            // Generate smooth area path
            const points = [...Array(40)].map((_, i) => {
              const x = (i / 40) * 100
              const y = 30 + Math.sin(i * 0.3 + expiryIdx) * 20 + Math.random() * 15
              return `${x},${y}`
            })

            const pathData = `M 0,100 L ${points.map((p, i) => {
              const [x, y] = p.split(',')
              return i === 0 ? `${x},${y}` : `L ${x},${y}`
            }).join(' ')} L 100,100 Z`

            const lineData = `M ${points.map((p, i) => {
              const [x, y] = p.split(',')
              return i === 0 ? `${x},${y}` : `L ${x},${y}`
            }).join(' ')}`

            return (
              <g key={expiry}>
                {/* Area Fill */}
                <path
                  d={pathData}
                  fill={color}
                  opacity={opacity * 0.3}
                  className="hover:opacity-50 transition-opacity cursor-pointer"
                />
                {/* Line */}
                <path
                  d={lineData}
                  stroke={color}
                  strokeWidth="2"
                  fill="none"
                  opacity={opacity}
                  className="hover:opacity-100 transition-opacity"
                />
              </g>
            )
          })}
        </svg>

        {/* X-Axis Time Labels (synced with main chart) */}
        <div className="absolute bottom-8 left-12 right-5 flex justify-between text-xs text-gray-500 font-mono">
          <div>09:30</div>
          <div>11:00</div>
          <div>12:30</div>
          <div>14:00</div>
          <div>15:30</div>
        </div>

        {/* Legend */}
        <div className="absolute bottom-2 left-12 flex gap-4 text-xs">
          {expiries.slice(0, 3).map((expiry, idx) => (
            <div key={expiry} className="flex items-center gap-2 bg-gray-800/80 backdrop-blur px-2 py-1 rounded">
              <div
                className="w-3 h-2 rounded"
                style={{
                  backgroundColor: activeTab?.color || '#3b82f6',
                  opacity: 0.8 - (idx * 0.2)
                }}
              />
              <span className="text-gray-300">{expiry}</span>
            </div>
          ))}
        </div>

        {/* Metric Label */}
        <div className="absolute top-2 left-12 bg-gray-800/90 backdrop-blur px-3 py-1.5 rounded text-sm font-semibold" style={{ color: activeTab?.color || '#3b82f6' }}>
          {activeTab?.label || 'Select a tab'} across Time
        </div>
      </div>
    </div>
  )
}
