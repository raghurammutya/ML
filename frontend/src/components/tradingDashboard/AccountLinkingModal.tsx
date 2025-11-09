/**
 * Account Linking Modal
 *
 * Allows users to link their Kite trading account by providing:
 * - Broker user ID
 * - API key
 * - API secret
 * - Optional account name
 *
 * Credentials are encrypted with KMS before storage in User Service.
 */

import { useState, FormEvent } from 'react'
import { useAuth } from '../../contexts/AuthContext'
import { linkTradingAccount, LinkAccountRequest } from '../../services/tradingAccounts'
import styles from './AccountLinkingModal.module.css'

interface AccountLinkingModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
}

export const AccountLinkingModal = ({ isOpen, onClose, onSuccess }: AccountLinkingModalProps) => {
  const { accessToken } = useAuth()
  const [broker] = useState<'kite'>('kite') // Currently only Kite is supported
  const [brokerUserId, setBrokerUserId] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [apiSecret, setApiSecret] = useState('')
  const [password, setPassword] = useState('')
  const [totpSeed, setTotpSeed] = useState('')
  const [accountName, setAccountName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!accessToken) {
      setError('Not authenticated. Please log in.')
      return
    }

    setLoading(true)
    setError(null)

    try {
      const accountData: LinkAccountRequest = {
        broker,
        broker_user_id: brokerUserId.trim().toUpperCase(),
        api_key: apiKey.trim(),
        api_secret: apiSecret.trim(),
        password: password.trim(),
        totp_seed: totpSeed.trim().replace(/\s+/g, '').toUpperCase(),
        account_name: accountName.trim() || `Kite - ${brokerUserId.trim().toUpperCase()}`
      }

      await linkTradingAccount(accessToken, accountData)

      // Success - reset form and close
      setBrokerUserId('')
      setApiKey('')
      setApiSecret('')
      setPassword('')
      setTotpSeed('')
      setAccountName('')
      onSuccess()
      onClose()
    } catch (err: any) {
      console.error('[AccountLinkingModal] Failed to link account:', err)
      setError(err.message || 'Failed to link account. Please check your credentials.')
    } finally {
      setLoading(false)
    }
  }

  const handleClose = () => {
    if (!loading) {
      setError(null)
      onClose()
    }
  }

  if (!isOpen) return null

  return (
    <div className={styles.overlay} onClick={handleClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.header}>
          <h2>Link Kite Account</h2>
          <button
            type="button"
            className={styles.closeButton}
            onClick={handleClose}
            disabled={loading}
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit} className={styles.form}>
          {error && (
            <div className={styles.error}>
              <strong>Error:</strong> {error}
            </div>
          )}

          <div className={styles.infoBox}>
            <p>
              <strong>Note:</strong> Your API credentials are encrypted with KMS before storage.
              Only you can access them.
            </p>
          </div>

          <div className={styles.field}>
            <label htmlFor="accountName">
              Account Name <span className={styles.optional}>(optional)</span>
            </label>
            <input
              id="accountName"
              type="text"
              placeholder="My Primary Account"
              value={accountName}
              onChange={(e) => setAccountName(e.target.value)}
              disabled={loading}
              maxLength={255}
            />
            <small>A friendly name to identify this account</small>
          </div>

          <div className={styles.field}>
            <label htmlFor="brokerUserId">
              Kite User ID <span className={styles.required}>*</span>
            </label>
            <input
              id="brokerUserId"
              type="text"
              placeholder="AB1234"
              value={brokerUserId}
              onChange={(e) => setBrokerUserId(e.target.value.toUpperCase())}
              required
              disabled={loading}
              maxLength={10}
              pattern="[A-Z0-9]+"
              title="Alphanumeric characters only"
            />
            <small>Your Zerodha client ID (e.g., AB1234)</small>
          </div>

          <div className={styles.field}>
            <label htmlFor="apiKey">
              API Key <span className={styles.required}>*</span>
            </label>
            <input
              id="apiKey"
              type="text"
              placeholder="your_api_key"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              required
              disabled={loading}
            />
            <small>
              Get from{' '}
              <a
                href="https://kite.zerodha.com/apps"
                target="_blank"
                rel="noopener noreferrer"
              >
                Kite Connect Apps
              </a>
            </small>
          </div>

          <div className={styles.field}>
            <label htmlFor="password">
              Broker Password <span className={styles.required}>*</span>
            </label>
            <input
              id="password"
              type="password"
              placeholder="Kite password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              disabled={loading}
              autoComplete="new-password"
            />
            <small>This is required to refresh sessions automatically.</small>
          </div>

          <div className={styles.field}>
            <label htmlFor="totpSeed">
              TOTP Secret <span className={styles.required}>*</span>
            </label>
            <input
              id="totpSeed"
              type="text"
              placeholder="BASE32 secret from Kite"
              value={totpSeed}
              onChange={(e) => setTotpSeed(e.target.value)}
              required
              disabled={loading}
            />
            <small>Enter the Base32 seed used by your authenticator app.</small>
          </div>

          <div className={styles.field}>
            <label htmlFor="apiSecret">
              API Secret <span className={styles.required}>*</span>
            </label>
            <input
              id="apiSecret"
              type="password"
              placeholder="your_api_secret"
              value={apiSecret}
              onChange={(e) => setApiSecret(e.target.value)}
              required
              disabled={loading}
              autoComplete="off"
            />
            <small>Keep this secret safe. It will be encrypted before storage.</small>
          </div>

          <div className={styles.actions}>
            <button
              type="button"
              onClick={handleClose}
              disabled={loading}
              className={styles.cancelButton}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={
                loading ||
                !brokerUserId ||
                !apiKey ||
                !apiSecret ||
                !password ||
                !totpSeed
              }
              className={styles.submitButton}
            >
              {loading ? 'Linking...' : 'Link Account'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
