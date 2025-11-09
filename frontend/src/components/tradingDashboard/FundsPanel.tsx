/**
 * Funds Panel
 *
 * Displays margin and funds information from Kite:
 * - Equity and Commodity segments
 * - Available funds breakdown
 * - Utilized funds breakdown
 * - Net available margin
 * - Auto-refresh every 30 seconds
 */

import { useEffect, useState } from 'react'
import styles from './FundsPanel.module.css'
import { useAuth } from '../../contexts/AuthContext'
import { useTradingAccount } from '../../contexts/TradingAccountContext'
import { fetchMargins, MarginsResponse, formatINR } from '../../services/portfolio'
import { classNames } from '../../utils/classNames'

type SegmentView = 'equity' | 'commodity'

export const FundsPanel = () => {
  const { accessToken } = useAuth()
  const { selectedAccount } = useTradingAccount()
  const [view, setView] = useState<SegmentView>('equity')
  const [margins, setMargins] = useState<MarginsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

  useEffect(() => {
    if (!accessToken || !selectedAccount) {
      setLoading(false)
      return
    }

    const loadMargins = async () => {
      try {
        setError(null)
        const data = await fetchMargins(accessToken, selectedAccount.trading_account_id)
        setMargins(data)
        setLastUpdate(new Date())
      } catch (err: any) {
        console.error('[FundsPanel] Failed to fetch margins:', err)
        setError(err.message || 'Failed to fetch margins')
      } finally {
        setLoading(false)
      }
    }

    loadMargins()

    // Poll every 30 seconds for margin updates
    const interval = setInterval(loadMargins, 30000)
    return () => clearInterval(interval)
  }, [accessToken, selectedAccount?.trading_account_id])

  if (!selectedAccount) {
    return (
      <div className={styles.wrapper}>
        <div className={styles.emptyState}>
          Select a trading account to view funds
        </div>
      </div>
    )
  }

  if (loading && !lastUpdate) {
    return (
      <div className={styles.wrapper}>
        <div className={styles.loading}>Loading funds...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className={styles.wrapper}>
        <div className={styles.error}>
          <strong>Error:</strong> {error}
        </div>
      </div>
    )
  }

  if (!margins) {
    return (
      <div className={styles.wrapper}>
        <div className={styles.emptyState}>No margin data available</div>
      </div>
    )
  }

  const segment = margins[view]

  if (!segment.enabled) {
    return (
      <div className={styles.wrapper}>
        <div className={styles.header}>
          <div className={styles.tabs}>
            <button
              className={classNames(styles.tab, view === 'equity' && styles.tabActive)}
              onClick={() => setView('equity')}
            >
              Equity
            </button>
            <button
              className={classNames(styles.tab, view === 'commodity' && styles.tabActive)}
              onClick={() => setView('commodity')}
            >
              Commodity
            </button>
          </div>
        </div>
        <div className={styles.emptyState}>
          {view === 'equity' ? 'Equity' : 'Commodity'} segment not enabled
        </div>
      </div>
    )
  }

  return (
    <div className={styles.wrapper}>
      <div className={styles.header}>
        <div className={styles.tabs}>
          <button
            className={classNames(styles.tab, view === 'equity' && styles.tabActive)}
            onClick={() => setView('equity')}
          >
            Equity
          </button>
          <button
            className={classNames(styles.tab, view === 'commodity' && styles.tabActive)}
            onClick={() => setView('commodity')}
          >
            Commodity
          </button>
        </div>
        {lastUpdate && (
          <div className={styles.lastUpdate}>
            Updated: {lastUpdate.toLocaleTimeString()}
          </div>
        )}
      </div>

      <div className={styles.netMargin}>
        <div className={styles.netLabel}>Net Available Margin</div>
        <div className={classNames(
          styles.netValue,
          segment.net >= 0 ? styles.positive : styles.negative
        )}>
          {formatINR(segment.net)}
        </div>
      </div>

      <div className={styles.sections}>
        {/* Available Funds */}
        <div className={styles.section}>
          <div className={styles.sectionHeader}>Available Funds</div>
          <div className={styles.items}>
            <div className={styles.item}>
              <span className={styles.itemLabel}>Cash</span>
              <span className={styles.itemValue}>{formatINR(segment.available.cash)}</span>
            </div>
            <div className={styles.item}>
              <span className={styles.itemLabel}>Opening Balance</span>
              <span className={styles.itemValue}>{formatINR(segment.available.opening_balance)}</span>
            </div>
            <div className={styles.item}>
              <span className={styles.itemLabel}>Live Balance</span>
              <span className={styles.itemValue}>{formatINR(segment.available.live_balance)}</span>
            </div>
            <div className={styles.item}>
              <span className={styles.itemLabel}>Collateral</span>
              <span className={styles.itemValue}>{formatINR(segment.available.collateral)}</span>
            </div>
            <div className={styles.item}>
              <span className={styles.itemLabel}>Intraday Payin</span>
              <span className={styles.itemValue}>{formatINR(segment.available.intraday_payin)}</span>
            </div>
            {segment.available.adhoc_margin > 0 && (
              <div className={styles.item}>
                <span className={styles.itemLabel}>Adhoc Margin</span>
                <span className={styles.itemValue}>{formatINR(segment.available.adhoc_margin)}</span>
              </div>
            )}
          </div>
        </div>

        {/* Utilized Funds */}
        <div className={styles.section}>
          <div className={styles.sectionHeader}>Utilized Funds</div>
          <div className={styles.items}>
            <div className={styles.item}>
              <span className={styles.itemLabel}>Debits</span>
              <span className={styles.itemValue}>{formatINR(segment.utilised.debits)}</span>
            </div>
            <div className={styles.item}>
              <span className={styles.itemLabel}>Exposure</span>
              <span className={styles.itemValue}>{formatINR(segment.utilised.exposure)}</span>
            </div>
            <div className={styles.item}>
              <span className={styles.itemLabel}>SPAN</span>
              <span className={styles.itemValue}>{formatINR(segment.utilised.span)}</span>
            </div>
            <div className={styles.item}>
              <span className={styles.itemLabel}>Option Premium</span>
              <span className={styles.itemValue}>{formatINR(segment.utilised.option_premium)}</span>
            </div>
            <div className={styles.item}>
              <span className={styles.itemLabel}>M2M Realised</span>
              <span className={classNames(
                styles.itemValue,
                segment.utilised.m2m_realised >= 0 ? styles.positive : styles.negative
              )}>
                {formatINR(segment.utilised.m2m_realised)}
              </span>
            </div>
            <div className={styles.item}>
              <span className={styles.itemLabel}>M2M Unrealised</span>
              <span className={classNames(
                styles.itemValue,
                segment.utilised.m2m_unrealised >= 0 ? styles.positive : styles.negative
              )}>
                {formatINR(segment.utilised.m2m_unrealised)}
              </span>
            </div>
            {segment.utilised.delivery > 0 && (
              <div className={styles.item}>
                <span className={styles.itemLabel}>Delivery</span>
                <span className={styles.itemValue}>{formatINR(segment.utilised.delivery)}</span>
              </div>
            )}
            {segment.utilised.holding_sales > 0 && (
              <div className={styles.item}>
                <span className={styles.itemLabel}>Holding Sales</span>
                <span className={styles.itemValue}>{formatINR(segment.utilised.holding_sales)}</span>
              </div>
            )}
            {segment.utilised.turnover > 0 && (
              <div className={styles.item}>
                <span className={styles.itemLabel}>Turnover</span>
                <span className={styles.itemValue}>{formatINR(segment.utilised.turnover)}</span>
              </div>
            )}
            {segment.utilised.payout > 0 && (
              <div className={styles.item}>
                <span className={styles.itemLabel}>Payout</span>
                <span className={styles.itemValue}>{formatINR(segment.utilised.payout)}</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default FundsPanel
