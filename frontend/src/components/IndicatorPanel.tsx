import React, { useState, useEffect } from 'react'

export interface IndicatorSettings {
  enabled: boolean
  pivot_color: string
  bc_color: string
  tc_color: string
  resistance_color: string
  support_color: string
  line_width: number
  line_style: 'solid' | 'dashed' | 'dotted'
}

export interface Indicator {
  id: string
  name: string
  description: string
  settings: IndicatorSettings
}

export interface CPRPoint {
  time: number
  pivot: number
  bc: number
  tc: number
  r1: number
  r2: number
  s1: number
  s2: number
}

interface IndicatorPanelProps {
  onIndicatorChange: (indicators: Indicator[]) => void
  onCPRDataChange: (data: CPRPoint[]) => void
  symbol: string
  timeframe: string
}

const DEFAULT_CPR_SETTINGS: IndicatorSettings = {
  enabled: false,
  pivot_color: '#FFEB3B',
  bc_color: '#FF5722',
  tc_color: '#4CAF50',
  resistance_color: '#2196F3',
  support_color: '#FF9800',
  line_width: 1,
  line_style: 'solid'
}

const IndicatorPanel: React.FC<IndicatorPanelProps> = ({
  onIndicatorChange,
  onCPRDataChange,
  symbol,
  timeframe
}) => {
  const [isOpen, setIsOpen] = useState(false)
  const [indicators, setIndicators] = useState<Indicator[]>([])
  const [cprSettings, setCprSettings] = useState<IndicatorSettings>(DEFAULT_CPR_SETTINGS)
  const [showCPRSettings, setShowCPRSettings] = useState(false)

  // Fetch available indicators on mount
  useEffect(() => {
    fetchAvailableIndicators()
  }, [])

  // Fetch CPR data when enabled or settings change
  useEffect(() => {
    if (cprSettings.enabled) {
      fetchCPRData()
    } else {
      onCPRDataChange([])
    }
  }, [cprSettings.enabled, symbol, timeframe])

  const fetchAvailableIndicators = async () => {
    try {
      const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/tradingview-api'
      const response = await fetch(`${API_BASE_URL}/indicators/available`)
      const data = await response.json()
      
      if (data.indicators) {
        const indicatorsWithSettings = data.indicators.map((ind: any) => ({
          ...ind,
          settings: {
            ...ind.settings,
            enabled: false
          }
        }))
        setIndicators(indicatorsWithSettings)
      }
    } catch (error) {
      console.error('Failed to fetch indicators:', error)
    }
  }

  const fetchCPRData = async () => {
    try {
      const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/tradingview-api'
      const now = Math.floor(Date.now() / 1000)
      const from = now - (30 * 24 * 3600) // Last 30 days
      
      const response = await fetch(
        `${API_BASE_URL}/indicators/cpr?symbol=${symbol}&from=${from}&to=${now}&resolution=${timeframe}`
      )
      const data = await response.json()
      
      if (data.status === 'ok' && data.data) {
        onCPRDataChange(data.data)
      }
    } catch (error) {
      console.error('Failed to fetch CPR data:', error)
    }
  }

  const toggleCPR = () => {
    const newSettings = { ...cprSettings, enabled: !cprSettings.enabled }
    setCprSettings(newSettings)
    
    // Update indicators list
    const updatedIndicators = indicators.map(ind => 
      ind.id === 'cpr' 
        ? { ...ind, settings: newSettings }
        : ind
    )
    setIndicators(updatedIndicators)
    onIndicatorChange(updatedIndicators)
  }

  const updateCPRSetting = (key: keyof IndicatorSettings, value: any) => {
    const newSettings = { ...cprSettings, [key]: value }
    setCprSettings(newSettings)
    
    // Update indicators list
    const updatedIndicators = indicators.map(ind => 
      ind.id === 'cpr' 
        ? { ...ind, settings: newSettings }
        : ind
    )
    setIndicators(updatedIndicators)
    onIndicatorChange(updatedIndicators)
  }

  return (
    <div style={{ position: 'relative', zIndex: 1000 }}>
      {/* Indicator Toggle Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        style={{
          position: 'absolute',
          top: '10px',
          right: '10px',
          backgroundColor: '#1e222d',
          color: '#d1d4dc',
          border: '1px solid #2b3245',
          borderRadius: '4px',
          padding: '8px 12px',
          cursor: 'pointer',
          fontSize: '12px',
          zIndex: 1001
        }}
      >
        📊 Indicators
      </button>

      {/* Indicator Panel */}
      {isOpen && (
        <div
          style={{
            position: 'absolute',
            top: '45px',
            right: '10px',
            backgroundColor: '#111826',
            border: '1px solid #1f2937',
            borderRadius: '8px',
            padding: '12px',
            minWidth: '280px',
            maxHeight: '400px',
            overflowY: 'auto',
            boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
            color: '#d1d4dc',
            fontSize: '12px',
            zIndex: 1002
          }}
        >
          <h3 style={{ margin: '0 0 12px 0', fontSize: '14px', fontWeight: 'bold' }}>
            Technical Indicators
          </h3>

          {/* CPR Section */}
          <div style={{ marginBottom: '12px' }}>
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '8px',
              backgroundColor: cprSettings.enabled ? '#1f2937' : 'transparent',
              borderRadius: '4px',
              cursor: 'pointer'
            }}
            onClick={toggleCPR}
            >
              <div>
                <div style={{ fontWeight: 'bold' }}>Central Pivot Range</div>
                <div style={{ fontSize: '10px', color: '#9aa4bf' }}>
                  Daily pivot points with S/R levels
                </div>
              </div>
              <input
                type="checkbox"
                checked={cprSettings.enabled}
                onChange={toggleCPR}
                style={{ cursor: 'pointer' }}
              />
            </div>

            {/* CPR Settings */}
            {cprSettings.enabled && (
              <div style={{
                marginTop: '8px',
                padding: '8px',
                backgroundColor: '#0f172a',
                borderRadius: '4px',
                border: '1px solid #1e293b'
              }}>
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: '8px'
                }}>
                  <span style={{ fontSize: '11px', fontWeight: 'bold' }}>Settings</span>
                  <button
                    onClick={() => setShowCPRSettings(!showCPRSettings)}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: '#9aa4bf',
                      cursor: 'pointer',
                      fontSize: '10px'
                    }}
                  >
                    {showCPRSettings ? '▲' : '▼'}
                  </button>
                </div>

                {showCPRSettings && (
                  <div style={{ display: 'grid', gap: '6px' }}>
                    {/* Line Width */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <label style={{ fontSize: '10px' }}>Line Width:</label>
                      <select
                        value={cprSettings.line_width}
                        onChange={(e) => updateCPRSetting('line_width', parseInt(e.target.value))}
                        style={{
                          backgroundColor: '#1e293b',
                          color: '#d1d4dc',
                          border: '1px solid #374151',
                          borderRadius: '2px',
                          padding: '2px 4px',
                          fontSize: '10px'
                        }}
                      >
                        <option value={1}>1px</option>
                        <option value={2}>2px</option>
                        <option value={3}>3px</option>
                      </select>
                    </div>

                    {/* Line Style */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <label style={{ fontSize: '10px' }}>Line Style:</label>
                      <select
                        value={cprSettings.line_style}
                        onChange={(e) => updateCPRSetting('line_style', e.target.value)}
                        style={{
                          backgroundColor: '#1e293b',
                          color: '#d1d4dc',
                          border: '1px solid #374151',
                          borderRadius: '2px',
                          padding: '2px 4px',
                          fontSize: '10px'
                        }}
                      >
                        <option value="solid">Solid</option>
                        <option value="dashed">Dashed</option>
                        <option value="dotted">Dotted</option>
                      </select>
                    </div>

                    {/* Color Settings */}
                    {[
                      { key: 'pivot_color', label: 'Pivot' },
                      { key: 'bc_color', label: 'BC' },
                      { key: 'tc_color', label: 'TC' },
                      { key: 'resistance_color', label: 'Resistance' },
                      { key: 'support_color', label: 'Support' }
                    ].map(({ key, label }) => (
                      <div key={key} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <label style={{ fontSize: '10px' }}>{label}:</label>
                        <input
                          type="color"
                          value={cprSettings[key as keyof IndicatorSettings] as string}
                          onChange={(e) => updateCPRSetting(key as keyof IndicatorSettings, e.target.value)}
                          style={{
                            width: '30px',
                            height: '20px',
                            border: 'none',
                            borderRadius: '2px',
                            cursor: 'pointer'
                          }}
                        />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Future indicators placeholder */}
          <div style={{ 
            padding: '8px',
            backgroundColor: '#0f172a',
            borderRadius: '4px',
            color: '#6b7280',
            fontSize: '10px',
            textAlign: 'center'
          }}>
            More indicators coming soon...
          </div>
        </div>
      )}
    </div>
  )
}

export default IndicatorPanel