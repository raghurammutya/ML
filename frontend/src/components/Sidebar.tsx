import React from 'react'
import { HealthStatus, CacheStats, LabelDistribution, LABEL_COLORS } from '../types'

interface SidebarProps {
  health: HealthStatus | null
  cacheStats: CacheStats | null
  labelDistribution: LabelDistribution | null
  selectedTimeframe: string
}

const Sidebar: React.FC<SidebarProps> = ({
  cacheStats,
  labelDistribution,
  selectedTimeframe
}) => {
  const formatNumber = (num: number): string => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`
    return num.toString()
  }

  const getTotalRequests = () => {
    if (!cacheStats) return 0
    return (cacheStats.l1_hits || 0) + (cacheStats.l2_hits || 0) + 
           (cacheStats.l3_hits || 0) + (cacheStats.total_misses || 0)
  }

  return (
    <div className="sidebar">
      <h2>System Analytics</h2>
      
      {/* Cache Statistics */}
      <div className="info-card">
        <h3>Cache Performance</h3>
        <div className="stats-grid">
          <div className="stat-item">
            <span className="stat-label">L1 Hits (Memory)</span>
            <span className="stat-value">{formatNumber(cacheStats?.l1_hits || 0)}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">L2 Hits (Redis)</span>
            <span className="stat-value">{formatNumber(cacheStats?.l2_hits || 0)}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">Cache Misses</span>
            <span className="stat-value">{formatNumber(cacheStats?.total_misses || 0)}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">Hit Rate</span>
            <span className="stat-value">{cacheStats?.hit_rate?.toFixed(1) || 0}%</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">Memory Entries</span>
            <span className="stat-value">{formatNumber(cacheStats?.memory_cache_size || 0)}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">Redis Keys</span>
            <span className="stat-value">{formatNumber(cacheStats?.redis_keys || 0)}</span>
          </div>
        </div>
      </div>

      {/* Label Distribution */}
      <div className="info-card">
        <h3>ML Label Distribution (Last 7 Days)</h3>
        <div className="label-distribution">
          {labelDistribution?.distribution && Object.entries(labelDistribution.distribution)
            .sort(([, a], [, b]) => b - a)
            .map(([label, count]) => (
              <div key={label} className="label-item">
                <div style={{ display: 'flex', alignItems: 'center' }}>
                  <div 
                    className="label-color" 
                    style={{ backgroundColor: LABEL_COLORS[label] || '#808080' }}
                  />
                  <span className="label-name">{label}</span>
                </div>
                <span className="label-count">{formatNumber(count)}</span>
              </div>
            ))}
        </div>
      </div>

      {/* System Metrics */}
      <div className="info-card">
        <h3>System Metrics</h3>
        <div className="stats-grid">
          <div className="stat-item">
            <span className="stat-label">Total Requests</span>
            <span className="stat-value">{formatNumber(getTotalRequests())}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">Current Timeframe</span>
            <span className="stat-value">{selectedTimeframe}m</span>
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="info-card">
        <h3>Quick Actions</h3>
        <button 
          onClick={() => window.location.reload()} 
          style={{
            width: '100%',
            padding: '8px',
            backgroundColor: '#2962ff',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
            fontSize: '14px'
          }}
        >
          Refresh Chart
        </button>
      </div>
    </div>
  )
}

export default Sidebar