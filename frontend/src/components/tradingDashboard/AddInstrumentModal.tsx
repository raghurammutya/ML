import { FormEvent, useEffect, useMemo, useState } from 'react'
import styles from './AddInstrumentModal.module.css'
import { useAuth } from '../../contexts/AuthContext'
import { addStrategyInstrument, AddInstrumentRequest } from '../../services/strategies'
import { searchTradableSymbols } from '../../services/instruments'

interface AddInstrumentModalProps {
  strategyId: number | null
  isOpen: boolean
  onClose: () => void
  onAdded: () => void
}

export const AddInstrumentModal = ({ strategyId, isOpen, onClose, onAdded }: AddInstrumentModalProps) => {
  const { accessToken } = useAuth()
  const [symbolQuery, setSymbolQuery] = useState('')
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [selectedSymbol, setSelectedSymbol] = useState('')
  const [direction, setDirection] = useState<'BUY' | 'SELL'>('BUY')
  const [quantity, setQuantity] = useState(75)
  const [entryPrice, setEntryPrice] = useState('')
  const [notes, setNotes] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isOpen) {
      setSymbolQuery('')
      setSuggestions([])
      setSelectedSymbol('')
      setDirection('BUY')
      setQuantity(75)
      setEntryPrice('')
      setNotes('')
      setError(null)
    }
  }, [isOpen])

  useEffect(() => {
    if (!symbolQuery.trim()) {
      setSuggestions([])
      return
    }
    const handle = window.setTimeout(async () => {
      try {
        const results = await searchTradableSymbols(symbolQuery.trim(), 20)
        setSuggestions(results)
      } catch (err) {
        console.error('[AddInstrumentModal] symbol search failed', err)
      }
    }, 250)
    return () => window.clearTimeout(handle)
  }, [symbolQuery])

  const canSubmit = useMemo(
    () =>
      Boolean(
        strategyId &&
          accessToken &&
          (selectedSymbol.trim() || symbolQuery.trim()) &&
          quantity > 0 &&
          Number(entryPrice) > 0,
      ),
    [strategyId, accessToken, selectedSymbol, symbolQuery, quantity, entryPrice],
  )

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (!strategyId || !accessToken || !canSubmit) return

    const payload: AddInstrumentRequest = {
      tradingsymbol: (selectedSymbol || symbolQuery).trim().toUpperCase(),
      direction,
      quantity,
      entry_price: Number(entryPrice),
      notes: notes.trim() || undefined,
    }

    setLoading(true)
    setError(null)
    try {
      await addStrategyInstrument(accessToken, strategyId, payload)
      onAdded()
      onClose()
    } catch (err: any) {
      console.error('[AddInstrumentModal] Failed to add instrument', err)
      setError(err.message || 'Failed to add instrument')
    } finally {
      setLoading(false)
    }
  }

  if (!isOpen) return null

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={(event) => event.stopPropagation()}>
        <header className={styles.header}>
          <h2>Add Instrument</h2>
          <button type="button" className={styles.closeButton} onClick={onClose} disabled={loading}>
            ×
          </button>
        </header>
        <form className={styles.form} onSubmit={handleSubmit}>
          {error && <div className={styles.error}>{error}</div>}
          <div className={styles.field}>
            <label htmlFor="symbol">Search Symbol *</label>
            <input
              id="symbol"
              type="text"
              value={symbolQuery}
              onChange={(event) => setSymbolQuery(event.target.value)}
              placeholder="e.g., NIFTY25N1123400CE"
              disabled={loading}
            />
            {suggestions.length > 0 && (
              <div className={styles.suggestionList}>
                {suggestions.map((symbol) => (
                  <button
                    type="button"
                    key={symbol}
                    onClick={() => {
                      setSelectedSymbol(symbol)
                      setSymbolQuery(symbol)
                    }}
                  >
                    {symbol}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className={styles.field}>
            <label>Direction *</label>
            <div className={styles.radioGroup}>
              <label>
                <input
                  type="radio"
                  name="direction"
                  value="BUY"
                  checked={direction === 'BUY'}
                  onChange={() => setDirection('BUY')}
                  disabled={loading}
                />
                Buy
              </label>
              <label>
                <input
                  type="radio"
                  name="direction"
                  value="SELL"
                  checked={direction === 'SELL'}
                  onChange={() => setDirection('SELL')}
                  disabled={loading}
                />
                Sell
              </label>
            </div>
          </div>
          <div className={styles.fieldRow}>
            <div className={styles.field}>
              <label htmlFor="quantity">Quantity *</label>
              <input
                id="quantity"
                type="number"
                min={1}
                step={1}
                value={quantity}
                onChange={(event) => setQuantity(Number(event.target.value))}
                disabled={loading}
              />
            </div>
            <div className={styles.field}>
              <label htmlFor="entryPrice">Entry Price *</label>
              <input
                id="entryPrice"
                type="number"
                min={0}
                step="0.05"
                value={entryPrice}
                onChange={(event) => setEntryPrice(event.target.value)}
                disabled={loading}
              />
              <small>Current: —</small>
            </div>
          </div>
          <div className={styles.field}>
            <label htmlFor="notes">Notes</label>
            <textarea
              id="notes"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              rows={3}
              disabled={loading}
              placeholder="Add optional execution notes"
            />
          </div>
          <div className={styles.actions}>
            <button type="button" onClick={onClose} className={styles.cancelButton} disabled={loading}>
              Cancel
            </button>
            <button type="submit" className={styles.submitButton} disabled={!canSubmit || loading}>
              {loading ? 'Adding…' : 'Add Instrument'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default AddInstrumentModal
