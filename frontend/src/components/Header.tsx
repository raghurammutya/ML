import React from 'react'
import { HealthStatus } from '../types'

const DEFAULT_CHART_SYMBOL =
  (import.meta.env.VITE_CHART_SYMBOL as string | undefined) ??
  (import.meta.env.VITE_MONITOR_SYMBOL as string | undefined) ??
  'NIFTY50'

interface HeaderProps {
  health: HealthStatus | null
}

const Header: React.FC<HeaderProps> = ({ health }) => {
  const formatUptime = (seconds: number): string => {
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    return `${hours}h ${minutes}m`
  }

  return (
    <div className="header">
      <h1>{DEFAULT_CHART_SYMBOL.toUpperCase()} - ML Label Visualization</h1>
      
      <div className="header-info">
        <div>
          <span className={`status-indicator ${health?.status === 'healthy' ? 'healthy' : 'unhealthy'}`}></span>
          System: {health?.status || 'checking...'}
        </div>
        
        <div>
          DB: {health?.database || 'unknown'}
        </div>
        
        <div>
          Redis: {health?.redis || 'unknown'}
        </div>
        
        <div>
          Hit Rate: {health?.cache_stats?.hit_rate?.toFixed(1) || '0'}%
        </div>
        
        <div>
          Uptime: {health ? formatUptime(health.uptime) : '-'}
        </div>
        
        <div>
          v{health?.version || '1.0.0'}
        </div>
      </div>
    </div>
  )
}

export default Header
