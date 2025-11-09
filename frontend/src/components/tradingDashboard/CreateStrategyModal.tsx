import { FormEvent, useState } from 'react'
import styles from './CreateStrategyModal.module.css'
import { useAuth } from '../../contexts/AuthContext'
import { useTradingAccount } from '../../contexts/TradingAccountContext'
import { useStrategy } from '../../contexts/StrategyContext'
import { createStrategy, CreateStrategyRequest } from '../../services/strategies'

interface CreateStrategyModalProps {
  isOpen: boolean
  onClose: () => void
}

export const CreateStrategyModal = ({ isOpen, onClose }: CreateStrategyModalProps) => {
  const { accessToken } = useAuth()
  const { selectedAccount } = useTradingAccount()
  const { refreshStrategies } = useStrategy()

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [tagsInput, setTagsInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const resetForm = () => {
    setName('')
    setDescription('')
    setTagsInput('')
  }

  const handleClose = () => {
    if (loading) return
    setError(null)
    onClose()
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (!accessToken || !selectedAccount) {
      setError('Select a trading account before creating strategies.')
      return
    }
    if (!name.trim()) {
      setError('Strategy name is required.')
      return
    }

    const payload: CreateStrategyRequest = {
      name: name.trim(),
      description: description.trim() || undefined,
      tags: tagsInput
        .split(',')
        .map((tag) => tag.trim())
        .filter(Boolean),
    }

    setLoading(true)
    setError(null)
    try {
      await createStrategy(accessToken, String(selectedAccount.trading_account_id), payload)
      await refreshStrategies()
      resetForm()
      onClose()
    } catch (err: any) {
      console.error('[CreateStrategyModal] Failed to create strategy', err)
      setError(err.message || 'Failed to create strategy')
    } finally {
      setLoading(false)
    }
  }

  if (!isOpen) return null

  return (
    <div className={styles.overlay} onClick={handleClose}>
      <div className={styles.modal} onClick={(event) => event.stopPropagation()}>
        <header className={styles.header}>
          <h2>Create Strategy</h2>
          <button type="button" className={styles.closeButton} onClick={handleClose} aria-label="Close" disabled={loading}>
            ×
          </button>
        </header>
        <form className={styles.form} onSubmit={handleSubmit}>
          {error && <div className={styles.error}>{error}</div>}
          <div className={styles.field}>
            <label htmlFor="strategyName">
              Strategy Name <span>*</span>
            </label>
            <input
              id="strategyName"
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g., Iron Condor - NIFTY"
              maxLength={120}
              disabled={loading}
              required
            />
          </div>
          <div className={styles.field}>
            <label htmlFor="strategyDescription">Description</label>
            <textarea
              id="strategyDescription"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Optional notes to describe entry, exit, and risk plan."
              rows={3}
              disabled={loading}
            />
          </div>
          <div className={styles.field}>
            <label htmlFor="strategyTags">Tags (comma-separated)</label>
            <input
              id="strategyTags"
              type="text"
              value={tagsInput}
              onChange={(event) => setTagsInput(event.target.value)}
              placeholder="theta, condor, weekly"
              disabled={loading}
            />
          </div>
          <div className={styles.actions}>
            <button type="button" className={styles.cancelButton} onClick={handleClose} disabled={loading}>
              Cancel
            </button>
            <button type="submit" className={styles.submitButton} disabled={loading || !name.trim()}>
              {loading ? 'Creating…' : 'Create Strategy'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default CreateStrategyModal
