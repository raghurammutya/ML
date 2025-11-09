/**
 * Trading Accounts Panel
 *
 * Displays list of trading accounts (owned + shared) with:
 * - Account selector dropdown
 * - Permission indicators
 * - Link account button
 * - Account status
 */

import { useState } from 'react'
import styles from './TradingAccountsPanel.module.css'
import { useTradingAccount } from '../../contexts/TradingAccountContext'
import { AccountLinkingModal } from './AccountLinkingModal'
import { getPermissionLabel } from '../../services/tradingAccounts'
import { classNames } from '../../utils/classNames'

export const TradingAccountsPanel = () => {
  const {
    ownedAccounts,
    sharedAccounts,
    allAccounts,
    selectedAccount,
    selectAccount,
    refreshAccounts,
    loading,
    error
  } = useTradingAccount()

  const [isLinkModalOpen, setIsLinkModalOpen] = useState(false)

  const handleLinkSuccess = () => {
    refreshAccounts()
  }

  if (loading) {
    return (
      <section className={styles.wrapper}>
        <div className={styles.loading}>Loading trading accounts...</div>
      </section>
    )
  }

  if (error) {
    return (
      <section className={styles.wrapper}>
        <div className={styles.error}>
          <strong>Error:</strong> {error}
          <button onClick={refreshAccounts} className={styles.retryButton}>
            Retry
          </button>
        </div>
      </section>
    )
  }

  return (
    <>
      <section className={styles.wrapper}>
        <header className={styles.header}>
          <span>Trading Accounts</span>
          <span className={styles.count}>{allAccounts.length}</span>
        </header>

        {allAccounts.length === 0 ? (
          <div className={styles.emptyState}>
            <p>No trading accounts linked.</p>
            <button
              onClick={() => setIsLinkModalOpen(true)}
              className={styles.linkButton}
            >
              Link Kite Account
            </button>
          </div>
        ) : (
          <>
            <div className={styles.accountSelector}>
              <label htmlFor="accountSelect">Active Account:</label>
              <select
                id="accountSelect"
                value={selectedAccount?.trading_account_id || ''}
                onChange={(e) => selectAccount(Number(e.target.value))}
                className={styles.select}
              >
                {ownedAccounts.length > 0 && (
                  <optgroup label="My Accounts">
                    {ownedAccounts.map((acc) => (
                      <option key={acc.trading_account_id} value={acc.trading_account_id}>
                        {acc.account_name} ({acc.broker_user_id})
                      </option>
                    ))}
                  </optgroup>
                )}
                {sharedAccounts.length > 0 && (
                  <optgroup label="Shared with Me">
                    {sharedAccounts.map((acc) => (
                      <option key={acc.trading_account_id} value={acc.trading_account_id}>
                        {acc.account_name} ({acc.broker_user_id})
                      </option>
                    ))}
                  </optgroup>
                )}
              </select>
            </div>

            {selectedAccount && (
              <div className={styles.accountInfo}>
                <div className={styles.infoRow}>
                  <span className={styles.label}>Broker:</span>
                  <span className={styles.value}>
                    {selectedAccount.broker.toUpperCase()}
                  </span>
                </div>
                <div className={styles.infoRow}>
                  <span className={styles.label}>User ID:</span>
                  <span className={styles.value}>{selectedAccount.broker_user_id}</span>
                </div>
                <div className={styles.infoRow}>
                  <span className={styles.label}>Status:</span>
                  <span
                    className={classNames(
                      styles.value,
                      styles.status,
                      selectedAccount.status === 'active' && styles.statusActive,
                      selectedAccount.status === 'credentials_expired' && styles.statusExpired
                    )}
                  >
                    {selectedAccount.status.replace('_', ' ')}
                  </span>
                </div>
                <div className={styles.infoRow}>
                  <span className={styles.label}>Access:</span>
                  <span className={styles.value}>
                    {selectedAccount.is_owner && <span className={styles.ownerBadge}>👑 Owner</span>}
                    {!selectedAccount.is_owner && (
                      <span className={styles.permissionBadge}>
                        {getPermissionLabel(selectedAccount.permissions)}
                      </span>
                    )}
                  </span>
                </div>
              </div>
            )}

            <div className={styles.actions}>
              <button
                onClick={() => setIsLinkModalOpen(true)}
                className={styles.linkButtonSecondary}
              >
                + Link Another Account
              </button>
            </div>
          </>
        )}
      </section>

      <AccountLinkingModal
        isOpen={isLinkModalOpen}
        onClose={() => setIsLinkModalOpen(false)}
        onSuccess={handleLinkSuccess}
      />
    </>
  )
}

export default TradingAccountsPanel
