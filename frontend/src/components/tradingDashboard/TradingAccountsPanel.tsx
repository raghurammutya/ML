import React from 'react'
import styles from './TradingAccountsPanel.module.css'
import { TradingAccount } from './tradingAccounts'
import { classNames } from '../../utils/classNames'

interface TradingAccountsPanelProps {
  accounts: TradingAccount[]
  onSelect: (accountId: string) => void
}

export const TradingAccountsPanel: React.FC<TradingAccountsPanelProps> = ({ accounts, onSelect }) => {
  if (!accounts.length) return null

  return (
    <section className={styles.wrapper}>
      <header className={styles.header}>
        <span>Trading Accounts</span>
        <span>{accounts.length}</span>
      </header>
      <div className={styles.list}>
        {accounts.map((account) => (
          <button
            key={account.id}
            type="button"
            className={styles.accountButton}
            onClick={() => onSelect(account.id)}
          >
            <div className={styles.accountDetails}>
              <span className={styles.username}>{account.username}</span>
              <span className={styles.exposure}>{account.exposureType}</span>
            </div>
            <div className={styles.metrics}>
              <span
                className={classNames(styles.pnl, account.pnl < 0 && styles.negative)}
              >
                {account.pnl >= 0 ? '+' : '−'}
                {Math.abs(account.pnl).toLocaleString('en-IN')}
              </span>
              <span className={styles.roi}>
                {account.roi >= 0 ? '+' : '−'}
                {Math.abs(account.roi).toFixed(1)}%
              </span>
            </div>
          </button>
        ))}
      </div>
    </section>
  )
}

export default TradingAccountsPanel

