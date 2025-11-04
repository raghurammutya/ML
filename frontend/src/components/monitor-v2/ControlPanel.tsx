import React from 'react'
import type { ControlPanelProps, Timeframe, IndicatorType } from '../../types/monitor-v2'

const TIMEFRAMES: Timeframe[] = ['1min', '5min', '15min', '30min', '1hour', '1day']
const INDICATORS: { value: IndicatorType; label: string }[] = [
  { value: 'iv', label: 'IV' },
  { value: 'delta', label: 'Delta' },
  { value: 'gamma', label: 'Gamma' },
  { value: 'theta', label: 'Theta' },
  { value: 'vega', label: 'Vega' },
  { value: 'volume', label: 'Volume' },
  { value: 'oi', label: 'OI' },
  { value: 'pcr', label: 'PCR' },
]

export const ControlPanel: React.FC<ControlPanelProps> = ({
  filters,
  onFiltersChange,
  timeframe,
  onTimeframeChange,
  replayState,
  onReplayToggle,
  onSaveLayout,
  onLoadLayout,
  savedLayouts,
}) => {
  const [selectedAccount, setSelectedAccount] = React.useState<number>(1)

  const containerStyle: React.CSSProperties = {
    backgroundColor: '#111827',
    borderBottom: '1px solid #374151',
    width: '100%',
  }

  const topBarStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '12px 24px',
    backgroundColor: '#1f2937',
    borderBottom: '1px solid #374151',
  }

  const accountButtonStyle = (isActive: boolean): React.CSSProperties => ({
    padding: '10px 32px',
    fontSize: '13px',
    fontWeight: 700,
    backgroundColor: isActive ? '#0891b2' : '#374151',
    color: '#ffffff',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
    transition: 'all 0.2s',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    minWidth: '140px',
  })

  const controlsBarStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: '16px',
    padding: '16px 24px',
    backgroundColor: '#111827',
  }

  const controlGroupStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    backgroundColor: '#1f2937',
    border: '1px solid #374151',
    borderRadius: '6px',
    padding: '6px 12px',
  }

  const labelStyle: React.CSSProperties = {
    fontSize: '9px',
    color: '#9ca3af',
    fontWeight: 600,
    textTransform: 'uppercase',
    whiteSpace: 'nowrap',
    marginRight: '4px',
  }

  const buttonStyle = (isActive: boolean): React.CSSProperties => ({
    padding: '4px 10px',
    borderRadius: '4px',
    fontSize: '10px',
    fontWeight: 600,
    backgroundColor: isActive ? '#2563eb' : '#374151',
    color: isActive ? '#ffffff' : '#d1d5db',
    border: 'none',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    transition: 'all 0.15s',
  })

  const selectStyle: React.CSSProperties = {
    backgroundColor: '#374151',
    color: '#e5e7eb',
    border: '1px solid #4b5563',
    borderRadius: '4px',
    padding: '4px 8px',
    fontSize: '10px',
    height: '28px',
    minWidth: '100px',
    outline: 'none',
    cursor: 'pointer',
  }

  return (
    <div style={containerStyle}>
      {/* Top Bar - Market Monitor & Accounts */}
      <div style={topBarStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
          <h1 style={{
            fontSize: '15px',
            fontWeight: 'bold',
            color: '#f9fafb',
            margin: 0,
            textTransform: 'uppercase',
            letterSpacing: '0.1em',
          }}>
            Market Monitor
          </h1>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '11px', color: '#9ca3af' }}>Underlying:</span>
            <span style={{ fontSize: '11px', color: '#f3f4f6', fontWeight: 600 }}>NIFTY50</span>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '12px' }}>
          {[1, 2, 3].map((acc) => (
            <button
              key={acc}
              onClick={() => setSelectedAccount(acc)}
              style={accountButtonStyle(selectedAccount === acc)}
              onMouseEnter={(e) => {
                if (selectedAccount !== acc) {
                  e.currentTarget.style.backgroundColor = '#4b5563'
                }
              }}
              onMouseLeave={(e) => {
                if (selectedAccount !== acc) {
                  e.currentTarget.style.backgroundColor = '#374151'
                }
              }}
            >
              Account {acc}
            </button>
          ))}
        </div>
      </div>

      {/* Controls Bar */}
      <div style={controlsBarStyle}>
        {/* Timeframe */}
        <div style={controlGroupStyle}>
          <span style={labelStyle}>TF</span>
          <div style={{ display: 'flex', gap: '4px' }}>
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf}
                onClick={() => onTimeframeChange(tf)}
                style={buttonStyle(timeframe === tf)}
                onMouseEnter={(e) => {
                  if (timeframe !== tf) {
                    e.currentTarget.style.backgroundColor = '#4b5563'
                  }
                }}
                onMouseLeave={(e) => {
                  if (timeframe !== tf) {
                    e.currentTarget.style.backgroundColor = '#374151'
                  }
                }}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>

        {/* Indicators */}
        <div style={controlGroupStyle}>
          <span style={labelStyle}>IND</span>
          <select
            multiple
            value={filters.indicators}
            onChange={(e) => {
              const selected = Array.from(e.target.selectedOptions, (opt) => opt.value) as IndicatorType[]
              onFiltersChange({ indicators: selected })
            }}
            style={selectStyle}
            size={1}
          >
            {INDICATORS.map((ind) => (
              <option key={ind.value} value={ind.value}>
                {ind.label}
              </option>
            ))}
          </select>
          <span style={{ fontSize: '9px', color: '#6b7280', fontWeight: 600 }}>
            {filters.indicators.length}
          </span>
        </div>

        {/* Expiries */}
        <div style={controlGroupStyle}>
          <span style={labelStyle}>EXP</span>
          <select
            multiple
            value={filters.selectedExpiries}
            onChange={(e) => {
              const selected = Array.from(e.target.selectedOptions, (opt) => opt.value)
              onFiltersChange({ selectedExpiries: selected })
            }}
            style={{ ...selectStyle, minWidth: '110px' }}
            size={1}
          >
            {filters.availableExpiries.map((expiry) => (
              <option key={expiry} value={expiry}>
                {expiry}
              </option>
            ))}
          </select>
          <span style={{ fontSize: '9px', color: '#6b7280', fontWeight: 600 }}>
            {filters.selectedExpiries.length}
          </span>
        </div>

        {/* Replay */}
        <button
          onClick={onReplayToggle}
          style={{
            ...buttonStyle(replayState.enabled),
            backgroundColor: replayState.enabled ? '#7c3aed' : '#374151',
            padding: '6px 14px',
          }}
          title={replayState.enabled ? 'Stop Replay' : 'Start Replay'}
        >
          {replayState.enabled ? '⏸' : '▶️'}
        </button>

        <div style={{ flex: 1 }} />

        {/* Save/Load */}
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            onClick={onSaveLayout}
            style={{ ...buttonStyle(false), padding: '6px 14px' }}
            title="Save current layout"
          >
            💾
          </button>
          <button
            onClick={onLoadLayout}
            style={{
              ...buttonStyle(false),
              padding: '6px 14px',
              opacity: savedLayouts.length === 0 ? 0.3 : 1,
              cursor: savedLayouts.length === 0 ? 'not-allowed' : 'pointer',
            }}
            title="Load saved layout"
            disabled={savedLayouts.length === 0}
          >
            📂
          </button>
        </div>
      </div>

      {/* Replay Controls */}
      {replayState.enabled && (
        <div style={{ marginTop: '24px', paddingTop: '24px', borderTop: '1px solid #374151' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <button style={{ ...buttonStyle(false), padding: '8px 16px' }}>
              {replayState.isPlaying ? '⏸ Pause' : '▶️ Play'}
            </button>
            <input
              type="range"
              min={replayState.startTime}
              max={replayState.endTime}
              value={replayState.currentTime}
              style={{ flex: 1, height: '8px', borderRadius: '4px' }}
            />
            <div style={{ fontSize: '11px', color: '#9ca3af', fontFamily: 'monospace', minWidth: '80px', textAlign: 'right' }}>
              {new Date(replayState.currentTime).toLocaleTimeString()}
            </div>
            <select style={{ ...selectStyle, width: '60px' }}>
              <option>1x</option>
              <option>2x</option>
              <option>5x</option>
              <option>10x</option>
            </select>
          </div>
        </div>
      )}
    </div>
  )
}
