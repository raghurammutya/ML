import { useMemo, useState } from 'react'
import styles from './StrategySelector.module.css'
import { useStrategy } from '../../contexts/StrategyContext'
import { formatCurrency } from '../../utils/format'
import CreateStrategyModal from './CreateStrategyModal'

export const StrategySelector = () => {
  const { strategies, selectedStrategy, selectStrategy, refreshStrategies, loading, error } = useStrategy()
  const [modalOpen, setModalOpen] = useState(false)

  const sorted = useMemo(() => {
    const defaultStrategies = strategies.filter((strategy) => strategy.is_default)
    const others = strategies.filter((strategy) => !strategy.is_default)
    return [...defaultStrategies, ...others]
  }, [strategies])

  const handleChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const strategyId = Number(event.target.value)
    if (!Number.isNaN(strategyId)) {
      selectStrategy(strategyId)
    }
  }

  return (
    <div className={styles.wrapper}>
      <div className={styles.header}>
        <div>
          <span className={styles.title}>Strategies</span>
          <span className={styles.count}>{strategies.length} Strategies</span>
        </div>
        <button type="button" className={styles.createButton} onClick={() => setModalOpen(true)}>
          + Create
        </button>
      </div>

      {loading && <div className={styles.status}>Loading strategies…</div>}
      {!loading && error && (
        <div className={styles.error}>
          <span>{error}</span>
          <button type="button" onClick={refreshStrategies}>
            Retry
          </button>
        </div>
      )}

      {!loading && !error && sorted.length > 0 && (
        <div className={styles.selector}>
          <select value={selectedStrategy?.strategy_id ?? ''} onChange={handleChange}>
            {sorted.map((strategy) => (
              <option key={strategy.strategy_id} value={strategy.strategy_id}>
                {strategy.name} ({formatCurrency(strategy.current_pnl)})
              </option>
            ))}
          </select>
          {selectedStrategy && (
            <div className={styles.summary}>
              <span className={styles.strategyName}>{selectedStrategy.name}</span>
              <span
                className={`${styles.pnl} ${
                  (selectedStrategy.current_pnl ?? 0) >= 0 ? styles.positive : styles.negative
                }`}
              >
                {formatCurrency(selectedStrategy.current_pnl)}
              </span>
            </div>
          )}
        </div>
      )}

      {!loading && !error && sorted.length === 0 && (
        <div className={styles.status}>
          <p>No strategies yet.</p>
          <button type="button" onClick={() => setModalOpen(true)}>
            Create Strategy
          </button>
        </div>
      )}

      <CreateStrategyModal
        isOpen={modalOpen}
        onClose={() => {
          setModalOpen(false)
        }}
      />
    </div>
  )
}

export default StrategySelector
