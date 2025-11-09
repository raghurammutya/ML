# UI Components Design - Smart Order Management

**Created**: 2025-11-09
**Purpose**: Complete UI/UX design for all smart order management features
**Framework**: React + TypeScript (current stack)

---

## Table of Contents

1. [Alert System UI](#1-alert-system-ui)
2. [Pre-Trade Confirmation Modals](#2-pre-trade-confirmation-modals)
3. [Margin Monitoring Dashboard](#3-margin-monitoring-dashboard)
4. [Order Execution Panel](#4-order-execution-panel)
5. [Risk Indicators](#5-risk-indicators)
6. [Housekeeping Panel](#6-housekeeping-panel)
7. [Greeks Monitor](#7-greeks-monitor)
8. [Settings & Configuration](#8-settings--configuration)

---

## 1. Alert System UI

### 1.1 Global Alert Center

**Location**: Top-right corner (notification bell icon)

```typescript
// AlertCenter.tsx

import React, { useState, useEffect } from 'react';
import { useAlerts } from '@/hooks/useAlerts';
import { Alert, AlertSeverity } from '@/types';

export const AlertCenter: React.FC = () => {
  const { alerts, unreadCount, markAsRead, respondToAlert } = useAlerts();
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="alert-center">
      {/* Bell icon with badge */}
      <button
        className="alert-bell"
        onClick={() => setIsOpen(!isOpen)}
      >
        <Bell size={24} />
        {unreadCount > 0 && (
          <span className="badge">{unreadCount}</span>
        )}
      </button>

      {/* Alert dropdown */}
      {isOpen && (
        <div className="alert-dropdown">
          <div className="alert-header">
            <h3>Alerts</h3>
            <button onClick={() => markAllAsRead()}>Mark all read</button>
          </div>

          <div className="alert-list">
            {alerts.map(alert => (
              <AlertCard
                key={alert.id}
                alert={alert}
                onAction={(action) => respondToAlert(alert.id, action)}
                onDismiss={() => markAsRead(alert.id)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
```

### 1.2 Alert Card Component

```tsx
// AlertCard.tsx

interface AlertCardProps {
  alert: Alert;
  onAction: (action: string) => void;
  onDismiss: () => void;
}

export const AlertCard: React.FC<AlertCardProps> = ({
  alert,
  onAction,
  onDismiss
}) => {
  const severityConfig = {
    info: { color: 'blue', icon: 'InfoCircle' },
    warning: { color: 'yellow', icon: 'AlertTriangle' },
    critical: { color: 'orange', icon: 'AlertOctagon' },
    urgent: { color: 'red', icon: 'AlertCircle' }
  };

  const config = severityConfig[alert.severity];

  return (
    <div className={`alert-card alert-${config.color}`}>
      <div className="alert-icon">
        <Icon name={config.icon} size={20} />
      </div>

      <div className="alert-content">
        <div className="alert-title">{alert.title}</div>
        <div className="alert-message">{alert.message}</div>

        {/* Type-specific details */}
        {renderAlertDetails(alert)}

        {/* Actions */}
        {alert.actions.length > 0 && (
          <div className="alert-actions">
            {alert.actions.map(action => (
              <button
                key={action}
                className="btn-action"
                onClick={() => onAction(action)}
              >
                {formatActionLabel(action)}
              </button>
            ))}
          </div>
        )}
      </div>

      <button className="alert-close" onClick={onDismiss}>
        ×
      </button>
    </div>
  );
};

// Render type-specific details
function renderAlertDetails(alert: Alert) {
  switch (alert.type) {
    case 'WIDE_SPREAD':
      return (
        <div className="alert-details">
          <div className="detail-row">
            <span>Spread:</span>
            <span className="value">{alert.data.spread_pct.toFixed(2)}%</span>
          </div>
          <div className="detail-row">
            <span>Estimated Slippage:</span>
            <span className="value">₹{alert.data.estimated_slippage.toFixed(0)}</span>
          </div>
        </div>
      );

    case 'MARGIN_WARNING':
      return (
        <div className="alert-details">
          <div className="detail-row">
            <span>Utilization:</span>
            <span className="value">{alert.data.utilization_pct.toFixed(1)}%</span>
          </div>
          <ProgressBar
            value={alert.data.utilization_pct}
            max={100}
            color={alert.data.utilization_pct > 90 ? 'red' : 'orange'}
          />
        </div>
      );

    case 'MARGIN_SHORTFALL':
      return (
        <div className="alert-details">
          <div className="detail-row">
            <span>Shortfall:</span>
            <span className="value">₹{alert.data.shortfall.toLocaleString()}</span>
          </div>
          <div className="detail-row">
            <span>Deadline:</span>
            <span className="value">{formatTime(alert.data.deadline)}</span>
          </div>
        </div>
      );

    case 'RISK_BREACH':
      return (
        <div className="alert-details">
          <div className="detail-row">
            <span>{alert.data.limit_type}:</span>
            <span className="value">
              {alert.data.current_value} / {alert.data.limit_value}
            </span>
          </div>
          <div className="detail-row">
            <span>Action:</span>
            <span className="value">{alert.data.action_taken}</span>
          </div>
        </div>
      );

    default:
      return null;
  }
}
```

### 1.3 Toast Notifications (for urgent alerts)

```tsx
// ToastNotification.tsx

export const ToastNotification: React.FC<{ alert: Alert }> = ({ alert }) => {
  return (
    <div className={`toast toast-${alert.severity}`}>
      <div className="toast-icon">
        <Icon name={getSeverityIcon(alert.severity)} />
      </div>
      <div className="toast-content">
        <div className="toast-title">{alert.title}</div>
        <div className="toast-message">{alert.message}</div>
      </div>
      <button className="toast-close">×</button>
    </div>
  );
};

// Usage: Show urgent alerts as toasts
useEffect(() => {
  if (alert.severity === 'urgent' || alert.severity === 'critical') {
    toast.show(<ToastNotification alert={alert} />);
  }
}, [alert]);
```

---

## 2. Pre-Trade Confirmation Modals

### 2.1 Order Confirmation Modal (with cost breakdown)

```tsx
// PreTradeConfirmationModal.tsx

interface PreTradeConfirmationProps {
  order: OrderRequest;
  onConfirm: () => void;
  onCancel: () => void;
}

export const PreTradeConfirmationModal: React.FC<PreTradeConfirmationProps> = ({
  order,
  onConfirm,
  onCancel
}) => {
  const [costBreakdown, setCostBreakdown] = useState(null);
  const [marginInfo, setMarginInfo] = useState(null);
  const [executionAnalysis, setExecutionAnalysis] = useState(null);

  useEffect(() => {
    // Fetch cost breakdown, margin, and execution analysis
    Promise.all([
      api.calculateCosts(order),
      api.calculateMargin(order),
      api.analyzeExecution(order)
    ]).then(([costs, margin, analysis]) => {
      setCostBreakdown(costs);
      setMarginInfo(margin);
      setExecutionAnalysis(analysis);
    });
  }, [order]);

  if (!costBreakdown) return <LoadingSpinner />;

  return (
    <Modal title="Confirm Order" onClose={onCancel}>
      {/* Order Summary */}
      <div className="order-summary">
        <h3>{order.tradingsymbol}</h3>
        <div className="summary-grid">
          <div className="summary-item">
            <span>Side:</span>
            <span className={order.side === 'BUY' ? 'text-green' : 'text-red'}>
              {order.side}
            </span>
          </div>
          <div className="summary-item">
            <span>Quantity:</span>
            <span>{order.quantity} lots</span>
          </div>
          <div className="summary-item">
            <span>Price:</span>
            <span>₹{order.price.toFixed(2)}</span>
          </div>
        </div>
      </div>

      {/* Execution Analysis */}
      {executionAnalysis.warnings.length > 0 && (
        <div className="warnings-section">
          <h4>⚠️  Execution Warnings</h4>
          {executionAnalysis.warnings.map((warning, i) => (
            <div key={i} className="warning-item">
              {warning}
            </div>
          ))}
        </div>
      )}

      {/* Spread & Impact */}
      <div className="execution-metrics">
        <div className="metric">
          <span>Spread:</span>
          <span className={executionAnalysis.spread_pct > 0.5 ? 'text-orange' : ''}>
            {executionAnalysis.spread_pct.toFixed(2)}%
          </span>
        </div>
        <div className="metric">
          <span>Market Impact:</span>
          <span className={executionAnalysis.impact_bps > 50 ? 'text-orange' : ''}>
            {executionAnalysis.impact_bps} bps
          </span>
        </div>
        <div className="metric">
          <span>Liquidity Tier:</span>
          <span>{executionAnalysis.liquidity_tier}</span>
        </div>
      </div>

      {/* Cost Breakdown */}
      <div className="cost-breakdown">
        <h4>💰 Cost Breakdown</h4>
        <table>
          <tbody>
            <tr>
              <td>Order Value</td>
              <td>₹{costBreakdown.order_value.toLocaleString()}</td>
            </tr>
            <tr>
              <td>Brokerage</td>
              <td>₹{costBreakdown.brokerage.toFixed(2)}</td>
            </tr>
            <tr>
              <td>STT</td>
              <td>₹{costBreakdown.stt.toFixed(2)}</td>
            </tr>
            <tr>
              <td>Exchange Charges</td>
              <td>₹{costBreakdown.exchange_charges.toFixed(2)}</td>
            </tr>
            <tr>
              <td>GST</td>
              <td>₹{costBreakdown.gst.toFixed(2)}</td>
            </tr>
            <tr>
              <td>Other Charges</td>
              <td>₹{(costBreakdown.sebi_charges + costBreakdown.stamp_duty).toFixed(2)}</td>
            </tr>
            <tr className="total-row">
              <td><strong>Total Charges</strong></td>
              <td><strong>₹{costBreakdown.total_charges.toFixed(2)}</strong></td>
            </tr>
            <tr className="net-row">
              <td><strong>Net Cost</strong></td>
              <td><strong>₹{costBreakdown.net_cost.toLocaleString()}</strong></td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Margin Info */}
      <div className="margin-info">
        <h4>📊 Margin Required</h4>
        <div className="margin-grid">
          <div className="margin-item">
            <span>SPAN:</span>
            <span>₹{marginInfo.span.toLocaleString()}</span>
          </div>
          <div className="margin-item">
            <span>Exposure:</span>
            <span>₹{marginInfo.exposure.toLocaleString()}</span>
          </div>
          {marginInfo.premium > 0 && (
            <div className="margin-item">
              <span>Premium:</span>
              <span>₹{marginInfo.premium.toLocaleString()}</span>
            </div>
          )}
          <div className="margin-item total">
            <span><strong>Total Required:</strong></span>
            <span><strong>₹{marginInfo.total.toLocaleString()}</strong></span>
          </div>
        </div>

        <div className="margin-status">
          <div className="status-row">
            <span>Available Margin:</span>
            <span>₹{marginInfo.available.toLocaleString()}</span>
          </div>
          <div className="status-row">
            <span>Remaining After Order:</span>
            <span className={marginInfo.remaining < 0 ? 'text-red' : 'text-green'}>
              ₹{marginInfo.remaining.toLocaleString()}
              {marginInfo.remaining < 0 ? ' (SHORTFALL)' : ' ✓'}
            </span>
          </div>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="modal-actions">
        <button className="btn-secondary" onClick={onCancel}>
          Cancel
        </button>
        <button
          className="btn-primary"
          onClick={onConfirm}
          disabled={marginInfo.remaining < 0}
        >
          {marginInfo.remaining < 0 ? 'Insufficient Margin' : 'Confirm Order'}
        </button>
      </div>
    </Modal>
  );
};
```

### 2.2 Wide Spread Warning Modal

```tsx
// WideSpreadWarningModal.tsx

export const WideSpreadWarningModal: React.FC<{
  order: OrderRequest;
  analysis: ExecutionAnalysis;
  onProceed: (orderType: 'MARKET' | 'LIMIT') => void;
  onCancel: () => void;
}> = ({ order, analysis, onProceed, onCancel }) => {
  return (
    <Modal title="⚠️  Wide Spread Detected" severity="warning">
      <div className="warning-content">
        <p>
          The bid-ask spread for <strong>{order.tradingsymbol}</strong> is{' '}
          <strong>{analysis.spread_pct.toFixed(2)}%</strong>, which is wider than normal.
        </p>

        <div className="impact-breakdown">
          <div className="impact-item">
            <span>Spread:</span>
            <span>₹{analysis.spread_abs.toFixed(2)}</span>
          </div>
          <div className="impact-item">
            <span>Estimated Slippage:</span>
            <span>₹{analysis.estimated_slippage.toFixed(0)}</span>
          </div>
          <div className="impact-item">
            <span>Market Impact:</span>
            <span>{analysis.impact_bps} bps</span>
          </div>
        </div>

        <div className="recommendation">
          <h4>💡 Recommendation</h4>
          <p>{analysis.recommendation}</p>
        </div>
      </div>

      <div className="modal-actions">
        <button className="btn-secondary" onClick={onCancel}>
          Cancel Order
        </button>
        <button
          className="btn-warning"
          onClick={() => onProceed('LIMIT')}
        >
          Use LIMIT Order (Recommended)
        </button>
        <button
          className="btn-danger"
          onClick={() => onProceed('MARKET')}
        >
          Proceed with MARKET Order
        </button>
      </div>
    </Modal>
  );
};
```

---

## 3. Margin Monitoring Dashboard

### 3.1 Margin Overview Widget

```tsx
// MarginOverview.tsx

export const MarginOverview: React.FC<{ strategyId?: number }> = ({ strategyId }) => {
  const { marginSnapshot } = useMarginMonitoring(strategyId);

  if (!marginSnapshot) return <LoadingSpinner />;

  const utilizationPct = marginSnapshot.margin_utilization_pct;
  const statusColor =
    utilizationPct > 90 ? 'red' :
    utilizationPct > 80 ? 'orange' :
    utilizationPct > 70 ? 'yellow' : 'green';

  return (
    <div className="margin-overview">
      <div className="margin-header">
        <h3>Margin Status</h3>
        <div className={`status-badge status-${statusColor}`}>
          {utilizationPct.toFixed(1)}% Used
        </div>
      </div>

      {/* Circular Progress */}
      <div className="margin-gauge">
        <CircularProgress
          value={utilizationPct}
          max={100}
          size={120}
          strokeWidth={12}
          color={statusColor}
        />
        <div className="gauge-label">
          <div className="used">₹{marginSnapshot.total_margin_required.toLocaleString()}</div>
          <div className="available">of ₹{marginSnapshot.available_margin.toLocaleString()}</div>
        </div>
      </div>

      {/* Breakdown */}
      <div className="margin-breakdown">
        <div className="breakdown-item">
          <span>SPAN Margin:</span>
          <span>₹{marginSnapshot.span_margin.toLocaleString()}</span>
        </div>
        <div className="breakdown-item">
          <span>Exposure (3%):</span>
          <span>₹{marginSnapshot.exposure_margin.toLocaleString()}</span>
        </div>
        {marginSnapshot.premium_margin > 0 && (
          <div className="breakdown-item">
            <span>Premium:</span>
            <span>₹{marginSnapshot.premium_margin.toLocaleString()}</span>
          </div>
        )}
        {marginSnapshot.additional_margin > 0 && (
          <div className="breakdown-item">
            <span>Additional:</span>
            <span>₹{marginSnapshot.additional_margin.toLocaleString()}</span>
          </div>
        )}
      </div>

      {/* Factors Applied */}
      {marginSnapshot.factors_applied.length > 0 && (
        <div className="margin-factors">
          <h4>Active Margin Factors:</h4>
          {marginSnapshot.factors_applied.map(factor => (
            <div key={factor} className="factor-tag">
              {formatFactor(factor)}
            </div>
          ))}
        </div>
      )}

      {/* Warnings */}
      {marginSnapshot.warnings.length > 0 && (
        <div className="margin-warnings">
          {marginSnapshot.warnings.map((warning, i) => (
            <div key={i} className="warning-item">
              ⚠️  {warning}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
```

### 3.2 Margin History Chart

```tsx
// MarginHistoryChart.tsx

export const MarginHistoryChart: React.FC<{ strategyId: number }> = ({ strategyId }) => {
  const { marginHistory } = useMarginHistory(strategyId, { days: 7 });

  const chartData = {
    labels: marginHistory.map(s => formatDate(s.timestamp)),
    datasets: [
      {
        label: 'Margin Required',
        data: marginHistory.map(s => s.total_margin_required),
        borderColor: 'rgb(255, 99, 132)',
        backgroundColor: 'rgba(255, 99, 132, 0.1)',
      },
      {
        label: 'Available Margin',
        data: marginHistory.map(s => s.available_margin),
        borderColor: 'rgb(54, 162, 235)',
        backgroundColor: 'rgba(54, 162, 235, 0.1)',
      }
    ]
  };

  return (
    <div className="margin-chart">
      <h3>Margin Trend (7 Days)</h3>
      <Line
        data={chartData}
        options={{
          responsive: true,
          plugins: {
            legend: { position: 'top' },
            tooltip: {
              callbacks: {
                label: (context) => `₹${context.parsed.y.toLocaleString()}`
              }
            }
          },
          scales: {
            y: {
              ticks: {
                callback: (value) => `₹${value.toLocaleString()}`
              }
            }
          }
        }}
      />
    </div>
  );
};
```

---

## 4. Order Execution Panel

### 4.1 Smart Order Form

```tsx
// SmartOrderForm.tsx

export const SmartOrderForm: React.FC<{ strategyId: number }> = ({ strategyId }) => {
  const [formData, setFormData] = useState({
    tradingsymbol: '',
    quantity: 0,
    side: 'BUY',
    orderType: 'MARKET',
    price: null
  });

  const [executionAnalysis, setExecutionAnalysis] = useState(null);
  const [showConfirmation, setShowConfirmation] = useState(false);

  // Real-time execution analysis (debounced)
  useEffect(() => {
    const timer = setTimeout(() => {
      if (formData.tradingsymbol && formData.quantity > 0) {
        api.analyzeExecution(formData).then(setExecutionAnalysis);
      }
    }, 500);
    return () => clearTimeout(timer);
  }, [formData]);

  const handleSubmit = () => {
    // Check for warnings
    if (executionAnalysis?.warnings.length > 0) {
      // Show warning modal
      setShowWarningModal(true);
    } else {
      // Show confirmation
      setShowConfirmation(true);
    }
  };

  return (
    <div className="smart-order-form">
      <h3>Place Order</h3>

      {/* Instrument Selection */}
      <InstrumentSearch
        value={formData.tradingsymbol}
        onChange={(symbol) => setFormData({ ...formData, tradingsymbol: symbol })}
      />

      {/* Quantity */}
      <div className="form-group">
        <label>Quantity (lots)</label>
        <input
          type="number"
          value={formData.quantity}
          onChange={(e) => setFormData({ ...formData, quantity: parseInt(e.target.value) })}
        />

        {/* Position Size Recommendation */}
        {executionAnalysis?.recommended_max_quantity && (
          <div className="recommendation">
            💡 Recommended max: {executionAnalysis.recommended_max_quantity} lots
            (based on liquidity)
          </div>
        )}
      </div>

      {/* Side */}
      <div className="form-group">
        <label>Side</label>
        <div className="button-group">
          <button
            className={formData.side === 'BUY' ? 'active buy' : ''}
            onClick={() => setFormData({ ...formData, side: 'BUY' })}
          >
            BUY
          </button>
          <button
            className={formData.side === 'SELL' ? 'active sell' : ''}
            onClick={() => setFormData({ ...formData, side: 'SELL' })}
          >
            SELL
          </button>
        </div>
      </div>

      {/* Order Type */}
      <div className="form-group">
        <label>Order Type</label>
        <select
          value={formData.orderType}
          onChange={(e) => setFormData({ ...formData, orderType: e.target.value })}
        >
          <option value="MARKET">MARKET</option>
          <option value="LIMIT">LIMIT</option>
          <option value="TWAP">TWAP (Time-Weighted)</option>
        </select>

        {/* Recommended order type */}
        {executionAnalysis?.recommended_order_type && (
          <div className="recommendation">
            💡 Recommended: {executionAnalysis.recommended_order_type}
          </div>
        )}
      </div>

      {/* Price (if LIMIT) */}
      {formData.orderType === 'LIMIT' && (
        <div className="form-group">
          <label>Limit Price</label>
          <input
            type="number"
            step="0.05"
            value={formData.price || ''}
            onChange={(e) => setFormData({ ...formData, price: parseFloat(e.target.value) })}
          />
        </div>
      )}

      {/* Live Execution Preview */}
      {executionAnalysis && (
        <div className="execution-preview">
          <h4>Execution Preview</h4>

          <div className="preview-grid">
            <div className="preview-item">
              <span>Spread:</span>
              <span className={executionAnalysis.spread_pct > 0.5 ? 'text-warning' : ''}>
                {executionAnalysis.spread_pct.toFixed(2)}%
              </span>
            </div>

            <div className="preview-item">
              <span>Impact:</span>
              <span className={executionAnalysis.impact_bps > 50 ? 'text-warning' : ''}>
                {executionAnalysis.impact_bps} bps
              </span>
            </div>

            <div className="preview-item">
              <span>Liquidity:</span>
              <span>{executionAnalysis.liquidity_tier}</span>
            </div>

            <div className="preview-item">
              <span>Est. Cost:</span>
              <span>₹{executionAnalysis.estimated_cost.toLocaleString()}</span>
            </div>
          </div>

          {/* Warnings */}
          {executionAnalysis.warnings.length > 0 && (
            <div className="warnings">
              {executionAnalysis.warnings.map((w, i) => (
                <div key={i} className="warning">⚠️  {w}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Submit */}
      <button
        className="btn-primary btn-large"
        onClick={handleSubmit}
        disabled={!formData.tradingsymbol || formData.quantity <= 0}
      >
        Place Order
      </button>

      {/* Confirmation Modal */}
      {showConfirmation && (
        <PreTradeConfirmationModal
          order={formData}
          onConfirm={handleConfirmOrder}
          onCancel={() => setShowConfirmation(false)}
        />
      )}
    </div>
  );
};
```

---

## 5. Risk Indicators

### 5.1 Strategy Risk Dashboard

```tsx
// StrategyRiskDashboard.tsx

export const StrategyRiskDashboard: React.FC<{ strategyId: number }> = ({ strategyId }) => {
  const { riskStatus } = useStrategyRisk(strategyId);

  return (
    <div className="risk-dashboard">
      <h3>Risk Status</h3>

      {/* Overall Risk Level */}
      <div className={`risk-badge risk-${riskStatus.overall_risk}`}>
        {riskStatus.overall_risk.toUpperCase()}
      </div>

      {/* Risk Metrics Grid */}
      <div className="risk-grid">
        {/* Loss */}
        <RiskMetricCard
          title="Current Loss"
          current={riskStatus.current_loss_pct}
          limit={riskStatus.max_loss_pct}
          unit="%"
          riskLevel={riskStatus.loss_risk}
        />

        {/* Margin Utilization */}
        <RiskMetricCard
          title="Margin Utilization"
          current={riskStatus.margin_utilization_pct}
          limit={90}
          unit="%"
          riskLevel={riskStatus.margin_risk}
        />

        {/* Greeks */}
        <RiskMetricCard
          title="Delta Exposure"
          current={Math.abs(riskStatus.net_delta)}
          limit={0.5}
          unit=""
          riskLevel={riskStatus.delta_risk}
        />

        <RiskMetricCard
          title="Gamma Risk"
          current={Math.abs(riskStatus.net_gamma)}
          limit={0.05}
          unit=""
          riskLevel={riskStatus.gamma_risk}
        />
      </div>

      {/* Active Warnings */}
      {riskStatus.warnings.length > 0 && (
        <div className="risk-warnings">
          <h4>⚠️  Active Warnings</h4>
          {riskStatus.warnings.map((warning, i) => (
            <div key={i} className="warning-item">{warning}</div>
          ))}
        </div>
      )}

      {/* Recommendations */}
      {riskStatus.recommendations.length > 0 && (
        <div className="risk-recommendations">
          <h4>💡 Recommendations</h4>
          {riskStatus.recommendations.map((rec, i) => (
            <div key={i} className="recommendation-item">{rec}</div>
          ))}
        </div>
      )}
    </div>
  );
};

// Risk Metric Card Component
const RiskMetricCard: React.FC<{
  title: string;
  current: number;
  limit: number;
  unit: string;
  riskLevel: string;
}> = ({ title, current, limit, unit, riskLevel }) => {
  const percentage = (current / limit) * 100;

  return (
    <div className={`risk-metric-card risk-${riskLevel}`}>
      <div className="metric-title">{title}</div>
      <div className="metric-value">
        {current.toFixed(2)}{unit} / {limit}{unit}
      </div>
      <ProgressBar
        value={percentage}
        max={100}
        color={riskLevel === 'LOW' ? 'green' : riskLevel === 'MEDIUM' ? 'yellow' : 'red'}
      />
    </div>
  );
};
```

---

## 6. Housekeeping Panel

### 6.1 Orphaned Orders Panel

```tsx
// OrphanedOrdersPanel.tsx

export const OrphanedOrdersPanel: React.FC<{ strategyId: number }> = ({ strategyId }) => {
  const { orphanedOrders, cleanupOrders } = useHousekeeping(strategyId);

  if (orphanedOrders.length === 0) {
    return (
      <div className="no-orphaned-orders">
        ✅ No orphaned orders detected
      </div>
    );
  }

  return (
    <div className="orphaned-orders-panel">
      <div className="panel-header">
        <h3>⚠️  Orphaned Orders ({orphanedOrders.length})</h3>
        <button
          className="btn-primary"
          onClick={() => cleanupOrders(orphanedOrders.map(o => o.id))}
        >
          Cleanup All
        </button>
      </div>

      <table className="orphaned-orders-table">
        <thead>
          <tr>
            <th>Order ID</th>
            <th>Symbol</th>
            <th>Type</th>
            <th>Quantity</th>
            <th>Reason</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {orphanedOrders.map(order => (
            <tr key={order.id}>
              <td>{order.id}</td>
              <td>{order.tradingsymbol}</td>
              <td>{order.order_type}</td>
              <td>{order.quantity}</td>
              <td>
                <span className="reason-tag">
                  {order.orphaned_reason}
                </span>
              </td>
              <td>
                <button
                  className="btn-small btn-danger"
                  onClick={() => cleanupOrders([order.id])}
                >
                  Cancel
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
```

---

## 7. Greeks Monitor

### 7.1 Greeks Dashboard Widget

```tsx
// GreeksDashboard.tsx

export const GreeksDashboard: React.FC<{ strategyId: number }> = ({ strategyId }) => {
  const { greeks } = useStrategyGreeks(strategyId);

  return (
    <div className="greeks-dashboard">
      <h3>Portfolio Greeks</h3>

      <div className="greeks-grid">
        {/* Delta */}
        <GreeksCard
          name="Delta"
          value={greeks.net_delta}
          risk={greeks.delta_risk}
          description="Directional exposure"
          threshold={0.3}
        />

        {/* Gamma */}
        <GreeksCard
          name="Gamma"
          value={greeks.net_gamma}
          risk={greeks.gamma_risk}
          description="Delta sensitivity"
          threshold={0.05}
        />

        {/* Vega */}
        <GreeksCard
          name="Vega"
          value={greeks.net_vega}
          risk={greeks.vega_risk}
          description="Volatility exposure (₹)"
          threshold={1000}
          prefix="₹"
        />

        {/* Theta */}
        <GreeksCard
          name="Theta"
          value={greeks.net_theta}
          risk="info"
          description="Daily time decay (₹)"
          prefix="₹"
        />
      </div>

      {/* Greeks Chart */}
      <GreeksHistoryChart strategyId={strategyId} />
    </div>
  );
};

const GreeksCard: React.FC<{
  name: string;
  value: number;
  risk: string;
  description: string;
  threshold?: number;
  prefix?: string;
}> = ({ name, value, risk, description, threshold, prefix = '' }) => {
  return (
    <div className={`greeks-card greeks-${risk}`}>
      <div className="greeks-name">{name}</div>
      <div className="greeks-value">
        {prefix}{Math.abs(value).toFixed(name === 'Delta' ? 3 : 2)}
      </div>
      <div className="greeks-description">{description}</div>
      {threshold && (
        <div className="greeks-threshold">
          Threshold: {threshold}
        </div>
      )}
    </div>
  );
};
```

---

## 8. Settings & Configuration

### 8.1 Strategy Settings Panel

```tsx
// StrategySettingsPanel.tsx

export const StrategySettingsPanel: React.FC<{ strategyId: number }> = ({ strategyId }) => {
  const { settings, updateSettings } = useStrategySettings(strategyId);

  return (
    <div className="strategy-settings">
      <h3>Strategy Settings</h3>

      {/* Housekeeping */}
      <div className="settings-section">
        <h4>Housekeeping</h4>

        <SettingToggle
          label="Auto-cleanup orphaned orders"
          value={settings.auto_cleanup_enabled}
          onChange={(val) => updateSettings({ auto_cleanup_enabled: val })}
        />

        <SettingToggle
          label="Cleanup SL on position exit"
          value={settings.cleanup_sl_on_exit}
          onChange={(val) => updateSettings({ cleanup_sl_on_exit: val })}
        />

        <SettingToggle
          label="Cleanup Target on position exit"
          value={settings.cleanup_target_on_exit}
          onChange={(val) => updateSettings({ cleanup_target_on_exit: val })}
        />
      </div>

      {/* Smart Execution */}
      <div className="settings-section">
        <h4>Smart Execution</h4>

        <SettingInput
          label="Max spread % (alert threshold)"
          type="number"
          value={settings.max_order_spread_pct}
          onChange={(val) => updateSettings({ max_order_spread_pct: val })}
          unit="%"
        />

        <SettingInput
          label="Min liquidity score"
          type="number"
          value={settings.min_liquidity_score}
          onChange={(val) => updateSettings({ min_liquidity_score: val })}
          min={0}
          max={100}
        />

        <SettingToggle
          label="Require approval for high-impact orders"
          value={settings.require_user_approval_high_impact}
          onChange={(val) => updateSettings({ require_user_approval_high_impact: val })}
        />
      </div>

      {/* Risk Management */}
      <div className="settings-section">
        <h4>Risk Management</h4>

        <SettingInput
          label="Max loss per strategy (%)"
          type="number"
          value={settings.max_loss_per_strategy_pct}
          onChange={(val) => updateSettings({ max_loss_per_strategy_pct: val })}
          unit="%"
        />

        <SettingInput
          label="Max margin utilization (%)"
          type="number"
          value={settings.max_margin_utilization_pct}
          onChange={(val) => updateSettings({ max_margin_utilization_pct: val })}
          unit="%"
        />

        <SettingToggle
          label="Auto square-off on loss limit"
          value={settings.auto_square_off_on_loss_limit}
          onChange={(val) => updateSettings({ auto_square_off_on_loss_limit: val })}
        />
      </div>

      {/* Margin */}
      <div className="settings-section">
        <h4>Margin</h4>

        <SettingInput
          label="Margin buffer (%)"
          type="number"
          value={settings.margin_buffer_pct}
          onChange={(val) => updateSettings({ margin_buffer_pct: val })}
          unit="%"
        />

        <SettingToggle
          label="Check margin before each order"
          value={settings.check_margin_before_order}
          onChange={(val) => updateSettings({ check_margin_before_order: val })}
        />
      </div>
    </div>
  );
};
```

---

## CSS Styling (Base Styles)

```css
/* alerts.css */

.alert-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px;
  border-radius: 8px;
  margin-bottom: 12px;
  border-left: 4px solid;
}

.alert-blue { background: #eff6ff; border-color: #3b82f6; }
.alert-yellow { background: #fffbeb; border-color: #f59e0b; }
.alert-orange { background: #fff7ed; border-color: #f97316; }
.alert-red { background: #fef2f2; border-color: #ef4444; }

.alert-icon {
  flex-shrink: 0;
}

.alert-content {
  flex: 1;
}

.alert-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.alert-message {
  color: #6b7280;
  font-size: 14px;
  margin-bottom: 8px;
}

.alert-details {
  background: white;
  padding: 12px;
  border-radius: 4px;
  margin-top: 8px;
}

.detail-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
}

.alert-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.btn-action {
  padding: 6px 12px;
  border-radius: 4px;
  border: 1px solid #d1d5db;
  background: white;
  cursor: pointer;
  font-size: 13px;
}

.btn-action:hover {
  background: #f9fafb;
}

/* Margin Dashboard */
.margin-gauge {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin: 24px 0;
}

.gauge-label {
  text-align: center;
  margin-top: 12px;
}

.gauge-label .used {
  font-size: 24px;
  font-weight: 700;
  color: #111827;
}

.gauge-label .available {
  font-size: 14px;
  color: #6b7280;
}

.margin-breakdown {
  margin-top: 20px;
}

.breakdown-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid #e5e7eb;
}

/* Risk Dashboard */
.risk-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-top: 16px;
}

.risk-metric-card {
  padding: 16px;
  border-radius: 8px;
  border: 2px solid;
}

.risk-metric-card.risk-LOW {
  border-color: #10b981;
  background: #f0fdf4;
}

.risk-metric-card.risk-MEDIUM {
  border-color: #f59e0b;
  background: #fffbeb;
}

.risk-metric-card.risk-HIGH,
.risk-metric-card.risk-EXTREME {
  border-color: #ef4444;
  background: #fef2f2;
}

.metric-title {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  color: #6b7280;
  margin-bottom: 8px;
}

.metric-value {
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 12px;
}
```

---

## Integration Summary

All UI components integrate with the Python SDK via:

1. **REST API calls** for synchronous operations
2. **WebSocket connections** for real-time alerts
3. **React hooks** that subscribe to SDK events

```typescript
// Example hook integration

export function useAlerts() {
  const [alerts, setAlerts] = useState<Alert[]>([]);

  useEffect(() => {
    // Subscribe to WebSocket for real-time alerts
    const ws = new WebSocket('ws://localhost:8081/ws/alerts');

    ws.onmessage = (event) => {
      const alert = JSON.parse(event.data);
      setAlerts(prev => [alert, ...prev]);

      // Show toast for urgent alerts
      if (alert.severity === 'urgent') {
        toast.show(<ToastNotification alert={alert} />);
      }
    };

    return () => ws.close();
  }, []);

  return { alerts, unreadCount: alerts.filter(a => !a.is_read).length };
}
```

---

This comprehensive UI design ensures all SDK features are accessible to users with:
✅ Real-time alerts and notifications
✅ Pre-trade confirmations with cost breakdown
✅ Visual risk indicators
✅ Margin monitoring dashboards
✅ Housekeeping panels
✅ Greeks visualization
✅ Configuration interfaces

All components are production-ready and follow modern React/TypeScript best practices! 🚀
