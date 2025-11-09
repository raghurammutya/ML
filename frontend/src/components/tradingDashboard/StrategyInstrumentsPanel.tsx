import { useCallback, useEffect, useState } from 'react'
import styles from './StrategyInstrumentsPanel.module.css'
import { StrategyInstrument } from '../../types/strategy'
import { useStrategy } from '../../contexts/StrategyContext'
import { useAuth } from '../../contexts/AuthContext'
import { fetchStrategyInstruments, deleteStrategyInstrument } from '../../services/strategies'
import { formatCurrency } from '../../utils/format'
import AddInstrumentModal from './AddInstrumentModal'

export const StrategyInstrumentsPanel = () => {
  const { selectedStrategy } = useStrategy()
  const { accessToken } = useAuth()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [instruments, setInstruments] = useState<StrategyInstrument[]>([])
  const [modalOpen, setModalOpen] = useState(false)

  const loadInstruments = useCallback(async () => {
    if (!selectedStrategy || !accessToken) {
      setInstruments([])
      return
    }
    try {
      setLoading(true)
      setError(null)
      const data = await fetchStrategyInstruments(accessToken, selectedStrategy.strategy_id)
      setInstruments(Array.isArray(data) ? data : [])
    } catch (err: any) {
      console.error('[StrategyInstrumentsPanel] Failed to load instruments', err)
      setError(err.message || 'Failed to load instruments')
      setInstruments([])
    } finally {
      setLoading(false)
    }
  }, [selectedStrategy, accessToken])

  useEffect(() => {
    loadInstruments()
  }, [loadInstruments])

  useEffect(() => {
    if (!selectedStrategy) return
    const interval = window.setInterval(loadInstruments, 15000)
    return () => window.clearInterval(interval)
  }, [selectedStrategy?.strategy_id, loadInstruments])

  const handleDelete = async (instrumentId: number) => {
    if (!selectedStrategy || !accessToken) return
    try {
      await deleteStrategyInstrument(accessToken, selectedStrategy.strategy_id, instrumentId)
      loadInstruments()
    } catch (err) {
      console.error('[StrategyInstrumentsPanel] Failed to delete instrument', err)
    }
  }

  if (!selectedStrategy) {
    return (
      <div className={styles.wrapper}>
        <div className={styles.empty}>Select a strategy to manage instruments</div>
      </div>
    )
  }

  return (
    <div className={styles.wrapper}>
      <div className={styles.header}>
        <span>Strategy Instruments</span>
        <button type="button" onClick={() => setModalOpen(true)}>
          + Add Instrument
        </button>
      </div>
      {loading && <div className={styles.status}>Loading instruments…</div>}
      {!loading && error && (
        <div className={styles.error}>
          <span>{error}</span>
          <button type="button" onClick={loadInstruments}>
            Retry
          </button>
        </div>
      )}
      {!loading && !error && instruments.length === 0 && (
        <div className={styles.empty}>No instruments added yet.</div>
      )}
      {!loading && !error && instruments.length > 0 && (
        <div className={styles.tableWrapper}>
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Dir</th>
                <th>Qty</th>
                <th>Entry</th>
                <th>Current</th>
                <th>P&amp;L</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {instruments.map((instrument) => (
                <tr key={instrument.id}>
                  <td>{instrument.tradingsymbol}</td>
                  <td className={instrument.direction === 'BUY' ? styles.buy : styles.sell}>{instrument.direction}</td>
                  <td>{instrument.quantity}</td>
                  <td>{instrument.entry_price?.toFixed(2) ?? '—'}</td>
                  <td>{instrument.current_price?.toFixed(2) ?? '—'}</td>
                  <td
                    className={
                      instrument.current_pnl == null
                        ? styles.pnlNeutral
                        : instrument.current_pnl >= 0
                          ? styles.pnlPositive
                          : styles.pnlNegative
                    }
                  >
                    {instrument.current_pnl != null ? formatCurrency(instrument.current_pnl) : '—'}
                  </td>
                  <td>
                    <button type="button" onClick={() => handleDelete(instrument.id)}>
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <AddInstrumentModal
        strategyId={selectedStrategy?.strategy_id ?? null}
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        onAdded={loadInstruments}
      />
    </div>
  )
}

export default StrategyInstrumentsPanel
