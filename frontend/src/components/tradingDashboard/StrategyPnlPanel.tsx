import { useEffect, useState } from 'react'
import styles from './StrategyPnlPanel.module.css'
import { useStrategy } from '../../contexts/StrategyContext'
import { useAuth } from '../../contexts/AuthContext'
import { useTradingAccount } from '../../contexts/TradingAccountContext'
import { fetchStrategyDetails } from '../../services/strategies'
import { formatCurrency, formatNumber } from '../../utils/format'

interface StrategyMetrics {
  current_pnl: number
  current_m2m: number
  total_capital_deployed: number
  total_margin_used: number
  instrument_count: number
}

export const StrategyPnlPanel = () => {
  const { selectedStrategy } = useStrategy()
  const { accessToken } = useAuth()
  const { selectedAccount } = useTradingAccount()

  const [metrics, setMetrics] = useState<StrategyMetrics | null>(null)
  const [lastUpdated, setLastUpdated] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (selectedStrategy) {
      setMetrics({
        current_pnl: selectedStrategy.current_pnl,
        current_m2m: selectedStrategy.current_m2m,
        total_capital_deployed: selectedStrategy.total_capital_deployed,
        total_margin_used: selectedStrategy.total_margin_used,
        instrument_count: selectedStrategy.instrument_count,
      })
    } else {
      setMetrics(null)
    }
  }, [selectedStrategy])

  useEffect(() => {
    if (!selectedStrategy || !accessToken || !selectedAccount) return

    let cancelled = false

    const load = async () => {
      try {
        setLoading(true)
        const data = await fetchStrategyDetails(
          accessToken,
          String(selectedAccount.trading_account_id),
          selectedStrategy.strategy_id,
        )
        if (!cancelled) {
          setMetrics({
            current_pnl: data.current_pnl,
            current_m2m: data.current_m2m,
            total_capital_deployed: data.total_capital_deployed,
            total_margin_used: data.total_margin_used,
            instrument_count: data.instrument_count,
          })
          setLastUpdated(new Date().toLocaleTimeString('en-IN'))
        }
      } catch (error) {
        console.error('[StrategyPnlPanel] Failed to refresh metrics', error)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    const interval = window.setInterval(load, 5000)

    return () => {
      cancelled = true
      window.clearInterval(interval)
    }
  }, [selectedStrategy?.strategy_id, accessToken, selectedAccount])

  if (!selectedStrategy) {
    return (
      <div className={styles.wrapper}>
        <div className={styles.empty}>Select a strategy to view P&L</div>
      </div>
    )
  }

  const pnlClass =
    metrics && metrics.current_pnl >= 0 ? `${styles.currentPnl} ${styles.positive}` : `${styles.currentPnl} ${styles.negative}`

  return (
    <div className={styles.wrapper}>
      <div className={styles.header}>
        <div>
          <span className={styles.title}>Strategy P&amp;L</span>
          {loading && <span className={styles.badge}>Live</span>}
        </div>
        {lastUpdated && <span className={styles.timestamp}>Updated {lastUpdated}</span>}
      </div>
      <div className={styles.currentBlock}>
        <span>Current P&amp;L</span>
        <strong className={pnlClass}>{metrics ? formatCurrency(metrics.current_pnl) : '₹0.00'}</strong>
      </div>
      <div className={styles.metricsGrid}>
        <div>
          <label>M2M</label>
          <span>{metrics ? formatCurrency(metrics.current_m2m) : '₹0.00'}</span>
        </div>
        <div>
          <label>Capital</label>
          <span>{metrics ? formatCurrency(metrics.total_capital_deployed) : '₹0.00'}</span>
        </div>
        <div>
          <label>Margin Used</label>
          <span>{metrics ? formatCurrency(metrics.total_margin_used) : '₹0.00'}</span>
        </div>
        <div>
          <label>Instruments</label>
          <span>{metrics ? formatNumber(metrics.instrument_count) : '0'}</span>
        </div>
      </div>
    </div>
  )
}

export default StrategyPnlPanel
