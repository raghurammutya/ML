/**
 * Holdings Panel
 *
 * Displays long-term equity holdings from Kite:
 * - ISIN and exchange info
 * - Quantity breakdown (total, T1, authorized, collateral)
 * - Average price and current price
 * - P&L and day change calculations
 * - Auto-refresh every 60 seconds
 */

import { useEffect, useState } from 'react'
import styles from './HoldingsPanel.module.css'
import { useAuth } from '../../contexts/AuthContext'
import { useTradingAccount } from '../../contexts/TradingAccountContext'
import { fetchHoldings, Holding, formatINR, formatNumber, formatPercentage } from '../../services/portfolio'
import { classNames } from '../../utils/classNames'

export const HoldingsPanel = () => {
  const { accessToken } = useAuth()
  const { selectedAccount } = useTradingAccount()
  const [holdings, setHoldings] = useState<Holding[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

  useEffect(() => {
    if (!accessToken || !selectedAccount) {
      setLoading(false)
      return
    }

    const loadHoldings = async () => {
      try {
        setError(null)
        const data = await fetchHoldings(accessToken, selectedAccount.trading_account_id)
        setHoldings(data || [])
        setLastUpdate(new Date())
      } catch (err: any) {
        console.error('[HoldingsPanel] Failed to fetch holdings:', err)
        setError(err.message || 'Failed to fetch holdings')
      } finally {
        setLoading(false)
      }
    }

    loadHoldings()

    // Poll every 60 seconds (holdings change less frequently)
    const interval = setInterval(loadHoldings, 60000)
    return () => clearInterval(interval)
  }, [accessToken, selectedAccount?.trading_account_id])

  const totalPnL = holdings.reduce((sum, holding) => sum + (holding.pnl || 0), 0)
  const totalInvested = holdings.reduce((sum, holding) => sum + (holding.average_price * holding.quantity), 0)
  const totalCurrentValue = holdings.reduce((sum, holding) => sum + (holding.last_price * holding.quantity), 0)
  const totalDayChange = holdings.reduce((sum, holding) => sum + (holding.day_change || 0), 0)

  if (!selectedAccount) {
    return (
      <div className={styles.wrapper}>
        <div className={styles.emptyState}>
          Select a trading account to view holdings
        </div>
      </div>
    )
  }

  if (loading && !lastUpdate) {
    return (
      <div className={styles.wrapper}>
        <div className={styles.loading}>Loading holdings...</div>
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
        <div className={styles.title}>
          Holdings ({holdings.length})
        </div>
        {lastUpdate && (
          <div className={styles.lastUpdate}>
            Updated: {lastUpdate.toLocaleTimeString()}
          </div>
        )}
      </div>

      {holdings.length === 0 ? (
        <div className={styles.emptyState}>No holdings</div>
      ) : (
        <>
          <div className={styles.summary}>
            <div className={styles.summaryItem}>
              <span className={styles.summaryLabel}>Total Invested</span>
              <span className={styles.summaryValue}>
                {formatINR(totalInvested)}
              </span>
            </div>
            <div className={styles.summaryItem}>
              <span className={styles.summaryLabel}>Current Value</span>
              <span className={styles.summaryValue}>
                {formatINR(totalCurrentValue)}
              </span>
            </div>
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
              <span className={styles.summaryLabel}>Day Change</span>
              <span className={classNames(
                styles.summaryValue,
                totalDayChange >= 0 ? styles.positive : styles.negative
              )}>
                {formatINR(totalDayChange)}
              </span>
            </div>
          </div>

          <div className={styles.tableWrapper}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th className={styles.alignRight}>Qty</th>
                  <th className={styles.alignRight}>Avg Price</th>
                  <th className={styles.alignRight}>LTP</th>
                  <th className={styles.alignRight}>Invested</th>
                  <th className={styles.alignRight}>Current</th>
                  <th className={styles.alignRight}>P&L</th>
                  <th className={styles.alignRight}>Day Change</th>
                </tr>
              </thead>
              <tbody>
                {holdings.map((holding, idx) => {
                  const pnlClass = holding.pnl >= 0 ? styles.positive : styles.negative
                  const dayChangeClass = holding.day_change >= 0 ? styles.positive : styles.negative
                  const invested = holding.average_price * holding.quantity
                  const currentValue = holding.last_price * holding.quantity

                  return (
                    <tr key={idx} className={styles.row}>
                      <td>
                        <div className={styles.symbolCell}>
                          <span className={styles.symbol}>{holding.tradingsymbol}</span>
                          <span className={styles.exchange}>
                            {holding.exchange}
                            {holding.isin && (
                              <span className={styles.isin}> • {holding.isin}</span>
                            )}
                          </span>
                        </div>
                      </td>
                      <td className={styles.alignRight}>
                        <div className={styles.quantityCell}>
                          <span className={styles.quantity}>{formatNumber(holding.quantity, 0)}</span>
                          {(holding.t1_quantity > 0 || holding.collateral_quantity > 0) && (
                            <span className={styles.quantityDetails}>
                              {holding.t1_quantity > 0 && `T1: ${formatNumber(holding.t1_quantity, 0)}`}
                              {holding.collateral_quantity > 0 && ` Coll: ${formatNumber(holding.collateral_quantity, 0)}`}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className={styles.alignRight}>
                        {formatNumber(holding.average_price)}
                      </td>
                      <td className={styles.alignRight}>
                        {formatNumber(holding.last_price)}
                      </td>
                      <td className={styles.alignRight}>
                        {formatINR(invested)}
                      </td>
                      <td className={styles.alignRight}>
                        {formatINR(currentValue)}
                      </td>
                      <td className={classNames(styles.alignRight, pnlClass)}>
                        <div className={styles.pnlCell}>
                          <span>{formatINR(holding.pnl)}</span>
                          {holding.pnl !== 0 && invested > 0 && (
                            <span className={styles.pnlPercent}>
                              {formatPercentage((holding.pnl / invested) * 100, 1)}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className={classNames(styles.alignRight, dayChangeClass)}>
                        <div className={styles.dayChangeCell}>
                          <span>{formatINR(holding.day_change)}</span>
                          {holding.day_change_percentage !== undefined && (
                            <span className={styles.dayChangePercent}>
                              {formatPercentage(holding.day_change_percentage, 2)}
                            </span>
                          )}
                        </div>
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

export default HoldingsPanel
