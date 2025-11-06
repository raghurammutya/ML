import React, { useEffect, useMemo, useRef, useState } from 'react'
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid } from 'recharts'
import styles from './StrategyDrawer.module.css'
import { TradingAccount, StrategySnapshot } from './tradingAccounts'
import UnderlyingChart, { type UnderlyingChartProps } from '../nifty-monitor/UnderlyingChart'
import { useMonitorSync } from '../nifty-monitor/MonitorSyncContext'
import { classNames } from '../../utils/classNames'
import AnalyticsTabs from './AnalyticsTabs'
import {
  PositionRow,
  HoldingRow,
  OrderRow,
} from './portfolioMockData'
import { useFoAnalytics } from '../../hooks/useFoAnalytics'

interface StrategyDrawerProps {
  account: TradingAccount
  strategy: StrategySnapshot
  onSelectStrategy: (strategyId: string) => void
  onClose: () => void
}

interface MetricFrame {
  invested: number
  roi: number
  pnl: number
  pop: number
  maxProfit: number
  maxLoss: number
  profitLeft: number
  lossLeft: number
}

const DRAWER_UNDERLYING_MIN = 680
const DRAWER_UNDERLYING_MAX = 1120

const formatCurrency = (value: number) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(value)

const formatShort = (value: number) => {
  const sign = value < 0 ? '−' : ''
  const absolute = Math.abs(value)
  if (absolute >= 100000) return `${sign}${(absolute / 100000).toFixed(1)}L`
  if (absolute >= 1000) return `${sign}${(absolute / 1000).toFixed(1)}K`
  return `${sign}${absolute.toFixed(0)}`
}

const jitter = (base: number, percent: number) => {
  if (base === 0) return 0
  const offset = base * percent * (Math.random() - 0.5)
  return base + offset
}

const buildPayoffSeries = (metrics: MetricFrame) => {
  const points = []
  const steps = 26
  const base = metrics.pnl
  const range = Math.max(Math.abs(metrics.maxProfit), Math.abs(metrics.maxLoss), 1)
  for (let i = 0; i < steps; i += 1) {
    const pct = (i / (steps - 1)) * 100 - 50
    const distance = pct / 50
    const payoff =
      base +
      distance * (distance >= 0 ? metrics.profitLeft : -metrics.lossLeft) -
      (distance * distance * range) / 2
    points.push({
      move: pct,
      payoff,
    })
  }
  return points
}

const buildStrategyData = (
  account: TradingAccount,
  strategy: StrategySnapshot,
): { positions: PositionRow[]; holdings: HoldingRow[]; orders: OrderRow[] } => {
  const baseQuantity = strategy.metrics.invested > 0 ? Math.round(strategy.metrics.invested / 50000) * 25 : 50
  const syntheticOrderId = (suffix: string) => `${strategy.id}-${suffix}`

  const positions: PositionRow[] = [
    {
      id: `${strategy.id}-core`,
      symbol: `${strategy.symbol}-${strategy.name.replace(/\s+/g, '').slice(0, 8).toUpperCase()}`,
      instrument: 'Options Strategy',
      quantity: baseQuantity,
      avgPrice: Number((strategy.metrics.invested / Math.max(baseQuantity, 1)).toFixed(2)),
      ltp: Number((strategy.metrics.invested / Math.max(baseQuantity, 1) + strategy.metrics.pnl / Math.max(baseQuantity, 1)).toFixed(2)),
      pnl: strategy.metrics.pnl,
      roi: strategy.metrics.roi,
      status: 'Active',
      orders: [
        {
          id: syntheticOrderId('ord1'),
          parentId: `${strategy.id}-core`,
          symbol: strategy.symbol,
          side: 'Sell',
          quantity: Math.round(baseQuantity / 2),
          price: Number((strategy.metrics.invested / Math.max(baseQuantity, 1) * 1.06).toFixed(2)),
          status: 'Pending',
          type: 'Limit',
          timestamp: '08 Nov 15:05',
        },
        {
          id: syntheticOrderId('ord2'),
          parentId: `${strategy.id}-core`,
          symbol: strategy.symbol,
          side: 'Buy',
          quantity: Math.round(baseQuantity / 2),
          price: Number((strategy.metrics.invested / Math.max(baseQuantity, 1) * 0.94).toFixed(2)),
          status: 'Pending',
          type: 'Limit',
          timestamp: '08 Nov 14:58',
        },
      ],
    },
  ]

  const holdings: HoldingRow[] = [
    {
      id: `${strategy.id}-holding`,
      symbol: account.username.toUpperCase().slice(0, 4),
      quantity: Math.max(20, Math.round(baseQuantity / 2)),
      avgPrice: Number((strategy.metrics.invested / 1000).toFixed(2)),
      ltp: Number((strategy.metrics.invested / 1000 + strategy.metrics.pnl / 200).toFixed(2)),
      pnl: strategy.metrics.pnl / 3,
      roi: strategy.metrics.roi / 2,
      status: 'Active',
      pledgedQuantity: Math.max(0, Math.round(baseQuantity / 4)),
      orders: [
        {
          id: syntheticOrderId('hold-order'),
          parentId: `${strategy.id}-holding`,
          symbol: account.username.toUpperCase().slice(0, 4),
          side: 'Sell',
          quantity: Math.max(10, Math.round(baseQuantity / 4)),
          price: Number((strategy.metrics.invested / 1000 * 1.04).toFixed(2)),
          status: 'Pending',
          type: 'Limit',
          timestamp: '08 Nov 14:22',
        },
      ],
    },
  ]

  const orders: OrderRow[] = [
    {
      id: syntheticOrderId('live1'),
      parentId: null,
      symbol: strategy.symbol,
      side: 'Sell',
      quantity: Math.round(baseQuantity / 3),
      price: Number((strategy.metrics.invested / Math.max(baseQuantity, 1) * 1.08).toFixed(2)),
      status: 'Pending',
      type: 'Limit',
      timestamp: '08 Nov 15:10',
    },
    {
      id: syntheticOrderId('live2'),
      parentId: null,
      symbol: strategy.symbol,
      side: 'Buy',
      quantity: Math.round(baseQuantity / 3),
      price: Number((strategy.metrics.invested / Math.max(baseQuantity, 1) * 0.92).toFixed(2)),
      status: 'Pending',
      type: 'Limit',
      timestamp: '08 Nov 15:02',
    },
  ]

  return { positions, holdings, orders }
}

const StrategyDrawer: React.FC<StrategyDrawerProps> = ({
  account,
  strategy,
  onSelectStrategy,
  onClose,
}) => {
  const { crosshairRatio } = useMonitorSync()
  const [panelWidth, setPanelWidth] = useState<number>(DRAWER_UNDERLYING_MIN)
  const [surfaceMetrics, setSurfaceMetrics] = useState<{ left: number; width: number }>({
    left: 0,
    width: DRAWER_UNDERLYING_MIN,
  })
  const [metrics, setMetrics] = useState<MetricFrame>(strategy.metrics)
  const stackRef = useRef<HTMLDivElement | null>(null)
  const metricsRef = useRef<MetricFrame>(strategy.metrics)
  const payoffSeries = useMemo(() => buildPayoffSeries(metrics), [metrics])
  const strategyData = useMemo(() => buildStrategyData(account, strategy), [account, strategy])
  const strategyAnalytics = useFoAnalytics(strategy.symbol, strategy.timeframe)

  useEffect(() => {
    metricsRef.current = strategy.metrics
    setMetrics(strategy.metrics)
    setPanelWidth(Math.max(DRAWER_UNDERLYING_MIN, Math.min(DRAWER_UNDERLYING_MAX, panelWidth)))
  }, [strategy])

  useEffect(() => {
    const tick = () => {
      const base = metricsRef.current
      setMetrics({
        invested: base.invested,
        roi: jitter(base.roi, 0.012),
        pnl: jitter(base.pnl, 0.018),
        pop: Math.min(99, Math.max(0, jitter(base.pop, 0.006))),
        maxProfit: base.maxProfit,
        maxLoss: base.maxLoss,
        profitLeft: Math.max(0, jitter(base.profitLeft, 0.02)),
        lossLeft: Math.max(0, jitter(base.lossLeft, 0.02)),
      })
    }

    const interval = window.setInterval(tick, 1000)
    return () => window.clearInterval(interval)
  }, [])

  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose])

  useEffect(() => {
    if (!stackRef.current) return

    const stackEl = stackRef.current
    const resolveSurface = () =>
      (stackEl.querySelector('[data-surface-id="drawer-underlying"]') as HTMLElement | null) ?? null

    const updateMetrics = () => {
      const surface = resolveSurface()
      if (!surface) return
      const stackRect = stackEl.getBoundingClientRect()
      const surfaceRect = surface.getBoundingClientRect()
      setSurfaceMetrics({
        left: surfaceRect.left - stackRect.left,
        width: surfaceRect.width,
      })
    }

    updateMetrics()
    window.addEventListener('resize', updateMetrics)

    let resizeObserver: ResizeObserver | null = null
    const surface = resolveSurface()
    if (surface && typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(() => updateMetrics())
      resizeObserver.observe(surface)
    }

    return () => {
      window.removeEventListener('resize', updateMetrics)
      resizeObserver?.disconnect()
    }
  }, [panelWidth, strategy])

  const effectiveWidth = surfaceMetrics.width || panelWidth
  const effectiveOffset = surfaceMetrics.left
  const crosshairLeft =
    crosshairRatio != null && effectiveWidth
      ? effectiveOffset + crosshairRatio * effectiveWidth
      : null

  const handleBackdropClick = (event: React.MouseEvent<HTMLDivElement>) => {
    if (event.target === event.currentTarget) {
      onClose()
    }
  }

  const payoffNode = useMemo(() => {
    const values = payoffSeries.map((point) => point.payoff)
    const payoffMax = Math.max(...values, 1)
    const payoffMin = Math.min(...values, -1)

    return (
      <div style={{ width: '100%', height: 340 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={payoffSeries} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="rgba(148, 163, 184, 0.15)" strokeDasharray="3 3" />
            <XAxis
              dataKey="move"
              tick={{ fill: 'rgba(148, 163, 184, 0.8)', fontSize: 11 }}
              axisLine={{ stroke: 'rgba(148, 163, 184, 0.3)' }}
              tickLine={false}
              tickFormatter={(value) => `${value.toFixed(0)}%`}
            />
            <YAxis
              domain={[payoffMin * 1.1, payoffMax * 1.1]}
              tick={{ fill: 'rgba(148, 163, 184, 0.8)', fontSize: 11 }}
              axisLine={{ stroke: 'rgba(148, 163, 184, 0.3)' }}
              tickLine={false}
              tickFormatter={(value) => formatShort(value)}
            />
            <Area
              type="monotone"
              dataKey="payoff"
              stroke="#60a5fa"
              fill="#60a5fa"
              fillOpacity={0.25}
              strokeWidth={2}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    )
  }, [payoffSeries])

  return (
    <>
      <div
        className={classNames(styles.backdrop, styles.open)}
        onClick={handleBackdropClick}
        role="presentation"
      />
      <aside className={classNames(styles.drawer, styles.open)}>
        <div className={styles.drawerContent}>
          <header className={styles.header}>
            <div className={styles.headerInfo}>
              <span className={styles.headerTitle}>
                {account.username} • {strategy.name}
              </span>
              <div className={styles.headerMeta}>
                <span>Symbol: {strategy.symbol}</span>
                <span>Timeframe: {strategy.timeframe}</span>
                <span>Exposure: {account.exposureType}</span>
              </div>
            </div>
            <button type="button" className={styles.closeButton} onClick={onClose}>
              Close
            </button>
          </header>

          <nav className={styles.strategyTabs}>
            {account.strategies.map((item) => (
              <button
                key={item.id}
                type="button"
                className={classNames(
                  styles.strategyTab,
                  item.id === strategy.id && styles.strategyTabActive,
                )}
                onClick={() => onSelectStrategy(item.id)}
              >
                {item.name}
              </button>
            ))}
          </nav>

          <div className={styles.contentScroll}>
            <section className={styles.metricsGrid}>
              <div className={styles.metricCard}>
                <span className={styles.metricLabel}>Amount Invested</span>
                <span className={styles.metricValue}>{formatCurrency(metrics.invested)}</span>
              </div>
              <div className={styles.metricCard}>
                <span className={styles.metricLabel}>ROI</span>
                <span className={classNames(
                  styles.metricValue,
                  metrics.roi >= 0 ? styles.metricValuePositive : styles.metricValueNegative,
                )}>
                  {metrics.roi >= 0 ? '+' : '−'}
                  {Math.abs(metrics.roi).toFixed(2)}%
                </span>
              </div>
              <div className={styles.metricCard}>
                <span className={styles.metricLabel}>Current P&L</span>
                <span className={classNames(
                  styles.metricValue,
                  metrics.pnl >= 0 ? styles.metricValuePositive : styles.metricValueNegative,
                )}>
                  {metrics.pnl >= 0 ? '+' : '−'}
                  {formatShort(Math.abs(metrics.pnl))}
                </span>
              </div>
              <div className={styles.metricCard}>
                <span className={styles.metricLabel}>Probability of Profit</span>
                <span className={styles.metricValue}>{metrics.pop.toFixed(1)}%</span>
              </div>
              <div className={styles.metricCard}>
                <span className={styles.metricLabel}>Max Profit</span>
                <span className={classNames(styles.metricValue, styles.metricValuePositive)}>
                  +{formatShort(metrics.maxProfit)}
                </span>
              </div>
              <div className={styles.metricCard}>
                <span className={styles.metricLabel}>Max Loss</span>
                <span className={classNames(styles.metricValue, styles.metricValueNegative)}>
                  −{formatShort(metrics.maxLoss)}
                </span>
              </div>
              <div className={styles.metricCard}>
                <span className={styles.metricLabel}>Profit Left</span>
                <span className={classNames(styles.metricValue, styles.metricValuePositive)}>
                  +{formatShort(metrics.profitLeft)}
                </span>
              </div>
              <div className={styles.metricCard}>
                <span className={styles.metricLabel}>Loss Left</span>
                <span className={classNames(styles.metricValue, styles.metricValueNegative)}>
                  −{formatShort(metrics.lossLeft)}
                </span>
              </div>
            </section>

            <section className={styles.chartSection} ref={stackRef}>
              <div className={styles.resizeRow}>
                <label htmlFor="drawer-width">Underlying Width</label>
                <input
                  id="drawer-width"
                  type="range"
                  min={DRAWER_UNDERLYING_MIN}
                  max={DRAWER_UNDERLYING_MAX}
                  step={20}
                  value={panelWidth}
                  onChange={(event) => setPanelWidth(Number(event.target.value))}
                />
                <span>{panelWidth}px</span>
              </div>

              <div className={styles.chartFrame} style={{ width: panelWidth }}>
                <UnderlyingChart
                  key={`${strategy.id}-${strategy.timeframe}-drawer`}
                  symbol={strategy.symbol}
                  timeframe={strategy.timeframe as UnderlyingChartProps['timeframe']}
                  surfaceId="drawer-underlying"
                  reportDimensions
                  enableRealtime
                />
              </div>

              <AnalyticsTabs
                symbol={strategy.symbol}
                timeframe={strategy.timeframe}
                chartWidth={effectiveWidth}
                offsetLeft={effectiveOffset}
                crosshairLeft={crosshairLeft}
                positions={strategyData.positions}
                holdings={strategyData.holdings}
                orders={strategyData.orders}
                analyticsData={strategyAnalytics}
                payoffContent={
                  <div>
                    <h4 style={{ marginTop: 0, marginBottom: 12, color: '#f8fafc', fontSize: 14 }}>
                      Strategy Payoff (Simulated)
                    </h4>
                    {payoffNode}
                    <div className={styles.emptyPlaceholder}>Reserved space for strategy-specific widgets</div>
                  </div>
                }
              />
            </section>
          </div>
        </div>
      </aside>
    </>
  )
}

export default StrategyDrawer
