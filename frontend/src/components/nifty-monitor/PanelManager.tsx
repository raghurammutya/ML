import type { FoIndicatorDefinition } from '../../types'

interface PanelState {
  enabled: boolean
  collapsed: boolean
}

interface PanelManagerProps {
  indicators: FoIndicatorDefinition[]
  state: Record<string, PanelState>
  order: string[]
  onToggleEnabled: (id: string) => void
  onToggleCollapse: (id: string) => void
  onMove: (id: string, direction: 'up' | 'down') => void
  title: string
}

const PanelManager = ({ indicators, state, order, onToggleEnabled, onToggleCollapse, onMove, title }: PanelManagerProps) => {
  const orderedIndicators = order
    .map(id => indicators.find(i => i.id === id))
    .filter((i): i is FoIndicatorDefinition => Boolean(i))

  return (
    <div className="panel-manager">
      <div className="panel-manager__title">{title}</div>
      <div className="panel-manager__list">
        {orderedIndicators.map((indicator, index) => {
          const panelState = state[indicator.id]
          return (
            <div key={indicator.id} className="panel-manager__item">
              <div>
                <label className="panel-manager__label">
                  <input
                    type="checkbox"
                    checked={panelState?.enabled ?? false}
                    onChange={() => onToggleEnabled(indicator.id)}
                  />
                  <span>{indicator.label}</span>
                </label>
                <div className="panel-manager__meta">#{indicator.indicator}</div>
              </div>
              <div className="panel-manager__controls">
                <button onClick={() => onMove(indicator.id, 'up')} disabled={index === 0}>↑</button>
                <button onClick={() => onMove(indicator.id, 'down')} disabled={index === orderedIndicators.length - 1}>↓</button>
                <button onClick={() => onToggleCollapse(indicator.id)}>
                  {panelState?.collapsed ? 'Expand' : 'Collapse'}
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default PanelManager
