import React, { useMemo, useState } from 'react'
import styles from './AnalyticsTabs.module.css'
import OptionsRadar from './OptionsRadar'
import FoMoneynessCharts from './FoMoneynessCharts'
import {
  DEFAULT_POSITIONS,
  DEFAULT_HOLDINGS,
  DEFAULT_ORDERS,
  PositionRow,
  HoldingRow,
  OrderRow,
} from './portfolioMockData'
import { classNames } from '../../utils/classNames'
import type { FoAnalyticsState } from '../../hooks/useFoAnalytics'

type TabKey = 'greeks' | 'positions' | 'holdings' | 'orders' | 'payoff'

interface AnalyticsTabsProps {
  chartWidth: number
  offsetLeft: number
  symbol: string
  timeframe: string
  variant?: 'default' | 'compact'
  crosshairLeft: number | null
  positions?: PositionRow[]
  holdings?: HoldingRow[]
  orders?: OrderRow[]
  payoffContent?: React.ReactNode
  payoffPlaceholder?: string
  analyticsData: FoAnalyticsState
}

const TAB_DEFINITIONS: { key: TabKey; label: string }[] = [
  { key: 'greeks', label: 'Greeks' },
  { key: 'positions', label: 'Positions' },
  { key: 'holdings', label: 'Holdings' },
  { key: 'orders', label: 'Orders' },
  { key: 'payoff', label: 'Payoff' },
]

const AnalyticsTabs: React.FC<AnalyticsTabsProps> = ({
  chartWidth,
  offsetLeft,
  symbol,
  timeframe,
  variant = 'default',
  crosshairLeft,
  positions = DEFAULT_POSITIONS,
  holdings = DEFAULT_HOLDINGS,
  orders = DEFAULT_ORDERS,
  payoffContent,
  payoffPlaceholder = 'Payoff analytics placeholder. Connect strategy engine to populate.',
  analyticsData,
}) => {
  const [activeTab, setActiveTab] = useState<TabKey>('greeks')
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({})
  const analytics = analyticsData

  const wrapperStyle = {
    '--tab-width': `${chartWidth}px`,
    '--tab-offset': `${offsetLeft}px`,
  } as React.CSSProperties

  const toggleRow = (id: string) => {
    setExpandedRows((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  const renderStatusBadge = (status: string) => (
    <span className={classNames(styles.statusBadge, status === 'Closed' && styles.statusClosed)}>
      {status}
    </span>
  )

  const positionsContent = useMemo(
    () =>
      positions.map((position) => {
        const isExpanded = expandedRows[position.id]
        return (
          <div key={position.id} className={styles.accordionItem}>
            <button type="button" className={styles.accordionHeader} onClick={() => toggleRow(position.id)}>
              <div className={styles.accordionTitle}>
                <span className={styles.accordionToggle}>{isExpanded ? '−' : '+'}</span>
                <span className={styles.accordionSymbol}>{position.symbol}</span>
                <div className={styles.accordionMeta}>
                  <span>{position.instrument}</span>
                  <span>{position.quantity}</span>
                  <span>
                    Avg ₹{position.avgPrice.toFixed(2)} • LTP ₹{position.ltp.toFixed(2)}
                  </span>
                  <span className={position.pnl >= 0 ? styles.positive : styles.negative}>
                    {position.pnl >= 0 ? '+' : '−'}
                    ₹{Math.abs(position.pnl).toFixed(0)}
                  </span>
                  <span className={position.roi >= 0 ? styles.positive : styles.negative}>
                    {position.roi >= 0 ? '+' : '−'}
                    {Math.abs(position.roi).toFixed(1)}%
                  </span>
                </div>
              </div>
              {renderStatusBadge(position.status)}
            </button>
            {isExpanded && (
              <div className={styles.accordionBody}>
                <table className={classNames(styles.table, styles.ordersTable)}>
                  <thead>
                    <tr>
                      <th>Order Id</th>
                      <th>Side</th>
                      <th>Quantity</th>
                      <th>Price</th>
                      <th>Type</th>
                      <th>Status</th>
                      <th>Timestamp</th>
                    </tr>
                  </thead>
                  <tbody>
                    {position.orders.map((order) => (
                      <tr key={order.id}>
                        <td>{order.id}</td>
                        <td>{order.side}</td>
                        <td>{order.quantity}</td>
                        <td>₹{order.price.toFixed(2)}</td>
                        <td>{order.type}</td>
                        <td>{order.status}</td>
                        <td>{order.timestamp}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )
      }),
    [expandedRows, positions],
  )

  const holdingsContent = useMemo(
    () =>
      holdings.map((holding) => {
        const isExpanded = expandedRows[holding.id]
        return (
          <div key={holding.id} className={styles.accordionItem}>
            <button type="button" className={styles.accordionHeader} onClick={() => toggleRow(holding.id)}>
              <div className={styles.accordionTitle}>
                <span className={styles.accordionToggle}>{isExpanded ? '−' : '+'}</span>
                <span className={styles.accordionSymbol}>{holding.symbol}</span>
                <div className={styles.accordionMeta}>
                  <span>{holding.quantity} Qty</span>
                  <span>
                    Avg ₹{holding.avgPrice.toFixed(2)} • LTP ₹{holding.ltp.toFixed(2)}
                  </span>
                  <span>Pledged {holding.pledgedQuantity}</span>
                  <span className={holding.pnl >= 0 ? styles.positive : styles.negative}>
                    {holding.pnl >= 0 ? '+' : '−'}
                    ₹{Math.abs(holding.pnl).toFixed(0)}
                  </span>
                  <span className={holding.roi >= 0 ? styles.positive : styles.negative}>
                    {holding.roi >= 0 ? '+' : '−'}
                    {Math.abs(holding.roi).toFixed(1)}%
                  </span>
                </div>
              </div>
              {renderStatusBadge(holding.status)}
            </button>
            {isExpanded && (
              <div className={styles.accordionBody}>
                {holding.orders.length ? (
                  <table className={classNames(styles.table, styles.ordersTable)}>
                    <thead>
                      <tr>
                        <th>Order Id</th>
                        <th>Side</th>
                        <th>Quantity</th>
                        <th>Price</th>
                        <th>Type</th>
                        <th>Status</th>
                        <th>Timestamp</th>
                      </tr>
                    </thead>
                    <tbody>
                      {holding.orders.map((order) => (
                        <tr key={order.id}>
                          <td>{order.id}</td>
                          <td>{order.side}</td>
                          <td>{order.quantity}</td>
                          <td>₹{order.price.toFixed(2)}</td>
                          <td>{order.type}</td>
                          <td>{order.status}</td>
                          <td>{order.timestamp}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className={styles.payoffPlaceholder}>No working orders for this holding.</div>
                )}
              </div>
            )}
          </div>
        )
      }),
    [expandedRows, holdings],
  )

  const ordersContent = useMemo(
    () => (
      <div className={styles.contentBody}>
        <div className={styles.ordersToolbar}>
          <h3 style={{ margin: 0, fontSize: 14, color: '#f8fafc' }}>Working Orders</h3>
          <div className={styles.ordersActions}>
            <button type="button" className={styles.actionButton}>
              Buy
            </button>
            <button type="button" className={styles.actionButton}>
              Sell
            </button>
          </div>
        </div>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Order Id</th>
              <th>Symbol</th>
              <th>Side</th>
              <th>Quantity</th>
              <th>Price</th>
              <th>Type</th>
              <th>Status</th>
              <th>Timestamp</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((order) => (
              <tr key={order.id}>
                <td>{order.id}</td>
                <td>{order.symbol}</td>
                <td>{order.side}</td>
                <td>{order.quantity}</td>
                <td>₹{order.price.toFixed(2)}</td>
                <td>{order.type}</td>
                <td>{order.status}</td>
                <td>{order.timestamp}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ),
    [orders],
  )

  return (
    <section className={classNames(styles.wrapper, variant === 'compact' && styles.compact)} style={wrapperStyle}>
      <nav className={styles.tabHeader}>
        {TAB_DEFINITIONS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            className={classNames(styles.tabButton, activeTab === tab.key && styles.tabButtonActive)}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <div className={styles.contentCard}>
        {activeTab === 'greeks' && crosshairLeft != null && (
          <div className={styles.crosshairGuide} style={{ left: `${crosshairLeft}px` }} />
        )}
        <div className={styles.contentBody}>
          {activeTab === 'greeks' && (
            <div className={styles.greeksColumn}>
              {analytics.error && <div className={styles.errorBanner}>{analytics.error}</div>}
              <FoMoneynessCharts
                panels={analytics.moneyness}
                loading={analytics.loading}
                variant={variant}
              />
              <OptionsRadar
                symbol={symbol}
                timeframe={timeframe}
                width={Math.max(Math.round(chartWidth * 0.2), 160)}
                values={analytics.radar.reduce<Record<string, number>>((acc, item) => {
                  acc[item.metric] = item.value
                  return acc
                }, {})}
              />
            </div>
          )}

          {activeTab === 'positions' && <div className={styles.accordionList}>{positionsContent}</div>}

          {activeTab === 'holdings' && <div className={styles.accordionList}>{holdingsContent}</div>}

          {activeTab === 'orders' && ordersContent}

          {activeTab === 'payoff' && (
            payoffContent ?? <div className={styles.payoffPlaceholder}>{payoffPlaceholder}</div>
          )}
        </div>
      </div>
    </section>
  )
}

export default AnalyticsTabs
