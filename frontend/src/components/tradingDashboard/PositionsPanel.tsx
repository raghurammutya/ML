/**
 * Positions Panel
 *
 * Displays real-time positions from Kite:
 * - Net positions (overall)
 * - Day positions (intraday)
 * - P&L calculations
 * - Auto-refresh every 5 seconds
 */

import { useEffect, useState } from 'react'
import styles from './PositionsPanel.module.css'
import { useAuth } from '../../contexts/AuthContext'
import { useTradingAccount } from '../../contexts/TradingAccountContext'
import { fetchPositions, Position, formatINR, formatNumber } from '../../services/portfolio'
import { classNames } from '../../utils/classNames'

type PositionView = 'net' | 'day'

export const PositionsPanel = () => {
  const { accessToken } = useAuth()
  const { selectedAccount } = useTradingAccount()
  const [view, setView] = useState<PositionView>('net')
  const [netPositions, setNetPositions] = useState<Position[]>([])
  const [dayPositions, setDayPositions] = useState<Position[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

  useEffect(() => {
    if (!accessToken || !selectedAccount) {
      setLoading(false)
      return
    }

    const loadPositions = async () => {
      try {
        setError(null)
        const data = await fetchPositions(accessToken, selectedAccount.trading_account_id)
        setNetPositions(data.net || [])
        setDayPositions(data.day || [])
        setLastUpdate(new Date())
      } catch (err: any) {
        console.error('[PositionsPanel] Failed to fetch positions:', err)
        setError(err.message || 'Failed to fetch positions')
      } finally {
        setLoading(false)
      }
    }

    loadPositions()

    // Poll every 5 seconds for real-time updates
    const interval = setInterval(loadPositions, 5000)
    return () => clearInterval(interval)
  }, [accessToken, selectedAccount?.trading_account_id])

  const positions = view === 'net' ? netPositions : dayPositions
  const totalPnL = positions.reduce((sum, pos) => sum + (pos.pnl || 0), 0)
  const totalM2M = positions.reduce((sum, pos) => sum + (pos.m2m || 0), 0)

  if (!selectedAccount) {
    return (
      <div className={styles.wrapper}>
        <div className={styles.emptyState}>
          Select a trading account to view positions
        </div>
      </div>
    )
  }

  if (loading && !lastUpdate) {
    return (
      <div className={styles.wrapper}>
        <div className={styles.loading}>Loading positions...</div>
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

  return (
    <div className={styles.wrapper}>
      <div className={styles.header}>
        <div className={styles.tabs}>
          <button
            className={classNames(styles.tab, view === 'net' && styles.tabActive)}
            onClick={() => setView('net')}
          >
            Net ({netPositions.length})
          </button>
          <button
            className={classNames(styles.tab, view === 'day' && styles.tabActive)}
            onClick={() => setView('day')}
          >
            Day ({dayPositions.length})
          </button>
        </div>
        {lastUpdate && (
          <div className={styles.lastUpdate}>
            Updated: {lastUpdate.toLocaleTimeString()}
          </div>
        )}
      </div>

      {positions.length === 0 ? (
        <div className={styles.emptyState}>No open positions</div>
      ) : (
        <>
          <div className={styles.summary}>
            <div className={styles.summaryItem}>
              <span className={styles.summaryLabel}>Total P&L</span>
              <span className={classNames(
                styles.summaryValue,
                totalPnL >= 0 ? styles.positive : styles.negative
              )}>
                {formatINR(totalPnL)}
              </span>
            </div>
            <div className={styles.summaryItem}>
              <span className={styles.summaryLabel}>Total M2M</span>
              <span className={classNames(
                styles.summaryValue,
                totalM2M >= 0 ? styles.positive : styles.negative
              )}>
                {formatINR(totalM2M)}
              </span>
            </div>
          </div>

          <div className={styles.tableWrapper}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Product</th>
                  <th className={styles.alignRight}>Qty</th>
                  <th className={styles.alignRight}>Avg</th>
                  <th className={styles.alignRight}>LTP</th>
                  <th className={styles.alignRight}>P&L</th>
                  <th className={styles.alignRight}>M2M</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos, idx) => {
                  const pnlClass = pos.pnl >= 0 ? styles.positive : styles.negative
                  const m2mClass = pos.m2m >= 0 ? styles.positive : styles.negative

                  return (
                    <tr key={idx} className={styles.row}>
                      <td>
                        <div className={styles.symbolCell}>
                          <span className={styles.symbol}>{pos.tradingsymbol}</span>
                          <span className={styles.exchange}>{pos.exchange}</span>
                        </div>
                      </td>
                      <td>
                        <span className={styles.badge}>{pos.product}</span>
                      </td>
                      <td className={styles.alignRight}>
                        <span className={pos.quantity >= 0 ? styles.buy : styles.sell}>
                          {pos.quantity >= 0 ? '+' : ''}{formatNumber(pos.quantity, 0)}
                        </span>
                      </td>
                      <td className={styles.alignRight}>
                        {formatNumber(pos.average_price)}
                      </td>
                      <td className={styles.alignRight}>
                        {formatNumber(pos.last_price)}
                      </td>
                      <td className={classNames(styles.alignRight, pnlClass)}>
                        {formatINR(pos.pnl)}
                      </td>
                      <td className={classNames(styles.alignRight, m2mClass)}>
                        {formatINR(pos.m2m)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

export default PositionsPanel
