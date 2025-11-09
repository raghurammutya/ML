# Phase 2.5 Day 3: Frontend Components - Implementation Prompt

**Date**: November 7, 2025
**Status**: Ready to Implement
**Prerequisites**: Day 1 (Database), Day 2 (M2M Worker) completed

---

## Overview

Implement 7 frontend React components to enable users to:
1. Select and view strategies
2. Create new strategies
3. View instruments in a strategy
4. Manually add instruments to strategies
5. View P&L metrics
6. Visualize real-time M2M with charts

---

## Architecture

```
TradingDashboard.tsx
│
├─ StrategyProvider (Context)
│  └─ Provides: currentStrategy, strategies, selectStrategy, createStrategy
│
├─ StrategySelector (Dropdown)
│  └─ Select active strategy from list
│
├─ CreateStrategyModal (Modal)
│  └─ Form to create new strategy
│
├─ StrategyInstrumentsPanel (Table)
│  └─ List instruments in strategy
│     └─ AddInstrumentModal (trigger)
│
├─ AddInstrumentModal (Modal)
│  └─ Form to add instrument to strategy
│
├─ StrategyPnlPanel (Metrics)
│  └─ Display P&L summary, max drawdown, win rate
│
└─ StrategyM2MChart (Chart)
   └─ Real-time M2M line chart (minute candles)
```

---

## Implementation Steps

### Step 1: Create Type Definitions

**File**: `frontend/src/types.ts` (add to existing)

```typescript
// Strategy types
export interface Strategy {
  strategy_id: number;
  strategy_name: string;
  trading_account_id: string;
  description?: string;
  status: 'active' | 'closed' | 'archived';
  is_default: boolean;
  tags?: string[];
  total_pnl?: number;
  current_m2m?: number;
  created_at: string;
  updated_at: string;
  instrument_count?: number;
}

export interface StrategyInstrument {
  id: number;
  strategy_id: number;
  tradingsymbol: string;
  exchange: 'NSE' | 'NFO' | 'BSE';
  instrument_token?: number;
  instrument_type?: 'CE' | 'PE' | 'FUT' | 'EQ';
  strike?: number;
  expiry?: string;
  underlying_symbol?: string;
  lot_size?: number;
  direction: 'BUY' | 'SELL';
  quantity: number;
  entry_price: number;
  current_price?: number;
  current_pnl?: number;
  added_at: string;
  notes?: string;
}

export interface M2MCandle {
  strategy_id: number;
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  instrument_count: number;
}

export interface CreateStrategyRequest {
  strategy_name: string;
  description?: string;
  tags?: string[];
}

export interface AddInstrumentRequest {
  tradingsymbol: string;
  exchange: 'NSE' | 'NFO' | 'BSE';
  direction: 'BUY' | 'SELL';
  quantity: number;
  entry_price: number;
  notes?: string;
}
```

---

### Step 2: Create Strategies Service

**File**: `frontend/src/services/strategies.ts` (new file)

```typescript
import { getAuthToken } from './auth';

const API_BASE = 'http://localhost:8081';

// Fetch all strategies for a trading account
export async function fetchStrategies(accountId: string): Promise<Strategy[]> {
  const token = getAuthToken();
  const response = await fetch(
    `${API_BASE}/strategies?account_id=${accountId}`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    }
  );

  if (!response.ok) {
    throw new Error('Failed to fetch strategies');
  }

  return response.json();
}

// Get a single strategy
export async function fetchStrategy(
  strategyId: number,
  accountId: string
): Promise<Strategy> {
  const token = getAuthToken();
  const response = await fetch(
    `${API_BASE}/strategies/${strategyId}?account_id=${accountId}`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    }
  );

  if (!response.ok) {
    throw new Error('Failed to fetch strategy');
  }

  return response.json();
}

// Create a new strategy
export async function createStrategy(
  accountId: string,
  data: CreateStrategyRequest
): Promise<Strategy> {
  const token = getAuthToken();
  const response = await fetch(
    `${API_BASE}/strategies?account_id=${accountId}`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(data),
    }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to create strategy');
  }

  return response.json();
}

// Update a strategy
export async function updateStrategy(
  strategyId: number,
  accountId: string,
  data: Partial<CreateStrategyRequest>
): Promise<Strategy> {
  const token = getAuthToken();
  const response = await fetch(
    `${API_BASE}/strategies/${strategyId}?account_id=${accountId}`,
    {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(data),
    }
  );

  if (!response.ok) {
    throw new Error('Failed to update strategy');
  }

  return response.json();
}

// Delete a strategy
export async function deleteStrategy(
  strategyId: number,
  accountId: string
): Promise<void> {
  const token = getAuthToken();
  const response = await fetch(
    `${API_BASE}/strategies/${strategyId}?account_id=${accountId}`,
    {
      method: 'DELETE',
      headers: {
        Authorization: `Bearer ${token}`,
      },
    }
  );

  if (!response.ok) {
    throw new Error('Failed to delete strategy');
  }
}

// Fetch instruments for a strategy
export async function fetchStrategyInstruments(
  strategyId: number,
  accountId: string
): Promise<StrategyInstrument[]> {
  const token = getAuthToken();
  const response = await fetch(
    `${API_BASE}/strategies/${strategyId}/instruments?account_id=${accountId}`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    }
  );

  if (!response.ok) {
    throw new Error('Failed to fetch instruments');
  }

  return response.json();
}

// Add an instrument to a strategy
export async function addInstrument(
  strategyId: number,
  accountId: string,
  data: AddInstrumentRequest
): Promise<StrategyInstrument> {
  const token = getAuthToken();
  const response = await fetch(
    `${API_BASE}/strategies/${strategyId}/instruments?account_id=${accountId}`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(data),
    }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to add instrument');
  }

  return response.json();
}

// Remove an instrument from a strategy
export async function removeInstrument(
  strategyId: number,
  instrumentId: number,
  accountId: string
): Promise<void> {
  const token = getAuthToken();
  const response = await fetch(
    `${API_BASE}/strategies/${strategyId}/instruments/${instrumentId}?account_id=${accountId}`,
    {
      method: 'DELETE',
      headers: {
        Authorization: `Bearer ${token}`,
      },
    }
  );

  if (!response.ok) {
    throw new Error('Failed to remove instrument');
  }
}

// Fetch M2M history for a strategy
export async function fetchStrategyM2M(
  strategyId: number,
  accountId: string,
  startTime?: string,
  endTime?: string
): Promise<M2MCandle[]> {
  const token = getAuthToken();
  const params = new URLSearchParams({ account_id: accountId });
  if (startTime) params.append('start_time', startTime);
  if (endTime) params.append('end_time', endTime);

  const response = await fetch(
    `${API_BASE}/strategies/${strategyId}/m2m?${params}`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    }
  );

  if (!response.ok) {
    throw new Error('Failed to fetch M2M data');
  }

  return response.json();
}
```

---

### Step 3: Create StrategyContext

**File**: `frontend/src/contexts/StrategyContext.tsx` (new file)

```typescript
import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { Strategy, CreateStrategyRequest } from '../types';
import {
  fetchStrategies,
  fetchStrategy,
  createStrategy as createStrategyAPI,
  updateStrategy as updateStrategyAPI,
  deleteStrategy as deleteStrategyAPI,
} from '../services/strategies';
import { useTradingAccount } from './TradingAccountContext';

interface StrategyContextValue {
  strategies: Strategy[];
  currentStrategy: Strategy | null;
  loading: boolean;
  error: string | null;
  selectStrategy: (strategyId: number) => Promise<void>;
  createStrategy: (data: CreateStrategyRequest) => Promise<Strategy>;
  updateStrategy: (strategyId: number, data: Partial<CreateStrategyRequest>) => Promise<void>;
  deleteStrategy: (strategyId: number) => Promise<void>;
  refreshStrategies: () => Promise<void>;
}

const StrategyContext = createContext<StrategyContextValue | undefined>(undefined);

export function useStrategy() {
  const context = useContext(StrategyContext);
  if (!context) {
    throw new Error('useStrategy must be used within StrategyProvider');
  }
  return context;
}

interface StrategyProviderProps {
  children: ReactNode;
}

export function StrategyProvider({ children }: StrategyProviderProps) {
  const { currentAccount } = useTradingAccount();
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [currentStrategy, setCurrentStrategy] = useState<Strategy | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load strategies when account changes
  useEffect(() => {
    if (currentAccount?.trading_account_id) {
      loadStrategies();
    }
  }, [currentAccount?.trading_account_id]);

  // Auto-select default strategy or first strategy
  useEffect(() => {
    if (strategies.length > 0 && !currentStrategy) {
      const defaultStrategy = strategies.find((s) => s.is_default);
      setCurrentStrategy(defaultStrategy || strategies[0]);
    }
  }, [strategies, currentStrategy]);

  async function loadStrategies() {
    if (!currentAccount?.trading_account_id) return;

    setLoading(true);
    setError(null);

    try {
      const data = await fetchStrategies(currentAccount.trading_account_id);
      setStrategies(data);
    } catch (err: any) {
      setError(err.message || 'Failed to load strategies');
      console.error('Failed to load strategies:', err);
    } finally {
      setLoading(false);
    }
  }

  async function selectStrategy(strategyId: number) {
    if (!currentAccount?.trading_account_id) return;

    setLoading(true);
    setError(null);

    try {
      const strategy = await fetchStrategy(strategyId, currentAccount.trading_account_id);
      setCurrentStrategy(strategy);
    } catch (err: any) {
      setError(err.message || 'Failed to select strategy');
      console.error('Failed to select strategy:', err);
    } finally {
      setLoading(false);
    }
  }

  async function createStrategyHandler(data: CreateStrategyRequest): Promise<Strategy> {
    if (!currentAccount?.trading_account_id) {
      throw new Error('No trading account selected');
    }

    const newStrategy = await createStrategyAPI(currentAccount.trading_account_id, data);
    setStrategies((prev) => [...prev, newStrategy]);
    setCurrentStrategy(newStrategy);
    return newStrategy;
  }

  async function updateStrategyHandler(
    strategyId: number,
    data: Partial<CreateStrategyRequest>
  ) {
    if (!currentAccount?.trading_account_id) return;

    const updated = await updateStrategyAPI(
      strategyId,
      currentAccount.trading_account_id,
      data
    );

    setStrategies((prev) =>
      prev.map((s) => (s.strategy_id === strategyId ? updated : s))
    );

    if (currentStrategy?.strategy_id === strategyId) {
      setCurrentStrategy(updated);
    }
  }

  async function deleteStrategyHandler(strategyId: number) {
    if (!currentAccount?.trading_account_id) return;

    await deleteStrategyAPI(strategyId, currentAccount.trading_account_id);

    setStrategies((prev) => prev.filter((s) => s.strategy_id !== strategyId));

    if (currentStrategy?.strategy_id === strategyId) {
      setCurrentStrategy(strategies[0] || null);
    }
  }

  async function refreshStrategies() {
    await loadStrategies();
  }

  const value: StrategyContextValue = {
    strategies,
    currentStrategy,
    loading,
    error,
    selectStrategy,
    createStrategy: createStrategyHandler,
    updateStrategy: updateStrategyHandler,
    deleteStrategy: deleteStrategyHandler,
    refreshStrategies,
  };

  return (
    <StrategyContext.Provider value={value}>{children}</StrategyContext.Provider>
  );
}
```

---

### Step 4: Create StrategySelector Component

**File**: `frontend/src/components/tradingDashboard/StrategySelector.tsx` (new file)

```typescript
import React, { useState } from 'react';
import { useStrategy } from '../../contexts/StrategyContext';
import CreateStrategyModal from './CreateStrategyModal';
import styles from './StrategySelector.module.css';

export default function StrategySelector() {
  const { strategies, currentStrategy, selectStrategy, loading } = useStrategy();
  const [showCreateModal, setShowCreateModal] = useState(false);

  const handleStrategyChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const strategyId = parseInt(e.target.value);
    selectStrategy(strategyId);
  };

  return (
    <div className={styles.strategySelector}>
      <label htmlFor="strategy-select">Strategy:</label>
      <select
        id="strategy-select"
        value={currentStrategy?.strategy_id || ''}
        onChange={handleStrategyChange}
        disabled={loading}
        className={styles.select}
      >
        {strategies.map((strategy) => (
          <option key={strategy.strategy_id} value={strategy.strategy_id}>
            {strategy.strategy_name}
            {strategy.is_default ? ' (Default)' : ''}
            {strategy.instrument_count ? ` • ${strategy.instrument_count} instruments` : ''}
          </option>
        ))}
      </select>

      <button
        className={styles.createButton}
        onClick={() => setShowCreateModal(true)}
        disabled={loading}
      >
        + New Strategy
      </button>

      {showCreateModal && (
        <CreateStrategyModal onClose={() => setShowCreateModal(false)} />
      )}
    </div>
  );
}
```

**File**: `frontend/src/components/tradingDashboard/StrategySelector.module.css` (new file)

```css
.strategySelector {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--surface-color, #1e1e1e);
  border-bottom: 1px solid var(--border-color, #333);
}

.strategySelector label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary, #999);
}

.select {
  flex: 1;
  max-width: 400px;
  padding: 8px 12px;
  background: var(--input-bg, #2a2a2a);
  border: 1px solid var(--border-color, #444);
  border-radius: 4px;
  color: var(--text-primary, #fff);
  font-size: 14px;
  cursor: pointer;
}

.select:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.createButton {
  padding: 8px 16px;
  background: var(--primary-color, #2196f3);
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.createButton:hover:not(:disabled) {
  background: var(--primary-hover, #1976d2);
}

.createButton:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
```

---

### Step 5: Create CreateStrategyModal Component

**File**: `frontend/src/components/tradingDashboard/CreateStrategyModal.tsx` (new file)

```typescript
import React, { useState } from 'react';
import { useStrategy } from '../../contexts/StrategyContext';
import styles from './CreateStrategyModal.module.css';

interface CreateStrategyModalProps {
  onClose: () => void;
}

export default function CreateStrategyModal({ onClose }: CreateStrategyModalProps) {
  const { createStrategy } = useStrategy();
  const [strategyName, setStrategyName] = useState('');
  const [description, setDescription] = useState('');
  const [tags, setTags] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!strategyName.trim()) {
      setError('Strategy name is required');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await createStrategy({
        strategy_name: strategyName.trim(),
        description: description.trim() || undefined,
        tags: tags
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean),
      });

      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to create strategy');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.header}>
          <h2>Create New Strategy</h2>
          <button className={styles.closeButton} onClick={onClose}>
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.field}>
            <label htmlFor="strategy-name">Strategy Name *</label>
            <input
              id="strategy-name"
              type="text"
              value={strategyName}
              onChange={(e) => setStrategyName(e.target.value)}
              placeholder="e.g., Iron Condor - Nov Week"
              required
              autoFocus
            />
          </div>

          <div className={styles.field}>
            <label htmlFor="description">Description</label>
            <textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description of the strategy..."
              rows={3}
            />
          </div>

          <div className={styles.field}>
            <label htmlFor="tags">Tags</label>
            <input
              id="tags"
              type="text"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="e.g., weekly, neutral, high-probability (comma-separated)"
            />
          </div>

          {error && <div className={styles.error}>{error}</div>}

          <div className={styles.actions}>
            <button type="button" onClick={onClose} disabled={loading}>
              Cancel
            </button>
            <button type="submit" disabled={loading}>
              {loading ? 'Creating...' : 'Create Strategy'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
```

**File**: `frontend/src/components/tradingDashboard/CreateStrategyModal.module.css` (new file)

```css
.modalOverlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: var(--surface-color, #1e1e1e);
  border-radius: 8px;
  width: 90%;
  max-width: 500px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid var(--border-color, #333);
}

.header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.closeButton {
  background: none;
  border: none;
  color: var(--text-secondary, #999);
  font-size: 28px;
  cursor: pointer;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.closeButton:hover {
  color: var(--text-primary, #fff);
}

.form {
  padding: 20px;
}

.field {
  margin-bottom: 20px;
}

.field label {
  display: block;
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary, #999);
}

.field input,
.field textarea {
  width: 100%;
  padding: 10px 12px;
  background: var(--input-bg, #2a2a2a);
  border: 1px solid var(--border-color, #444);
  border-radius: 4px;
  color: var(--text-primary, #fff);
  font-size: 14px;
  font-family: inherit;
}

.field input:focus,
.field textarea:focus {
  outline: none;
  border-color: var(--primary-color, #2196f3);
}

.error {
  padding: 12px;
  background: rgba(244, 67, 54, 0.1);
  border: 1px solid #f44336;
  border-radius: 4px;
  color: #f44336;
  font-size: 14px;
  margin-bottom: 20px;
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.actions button {
  padding: 10px 20px;
  border: none;
  border-radius: 4px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.actions button[type='button'] {
  background: var(--surface-hover, #2a2a2a);
  color: var(--text-primary, #fff);
}

.actions button[type='submit'] {
  background: var(--primary-color, #2196f3);
  color: white;
}

.actions button[type='button']:hover:not(:disabled) {
  background: var(--border-color, #333);
}

.actions button[type='submit']:hover:not(:disabled) {
  background: var(--primary-hover, #1976d2);
}

.actions button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
```

---

### Step 6: Create StrategyInstrumentsPanel Component

**File**: `frontend/src/components/tradingDashboard/StrategyInstrumentsPanel.tsx` (new file)

```typescript
import React, { useState, useEffect } from 'react';
import { useStrategy } from '../../contexts/StrategyContext';
import { useTradingAccount } from '../../contexts/TradingAccountContext';
import { StrategyInstrument } from '../../types';
import { fetchStrategyInstruments, removeInstrument } from '../../services/strategies';
import AddInstrumentModal from './AddInstrumentModal';
import styles from './StrategyInstrumentsPanel.module.css';

export default function StrategyInstrumentsPanel() {
  const { currentStrategy } = useStrategy();
  const { currentAccount } = useTradingAccount();
  const [instruments, setInstruments] = useState<StrategyInstrument[]>([]);
  const [loading, setLoading] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);

  useEffect(() => {
    if (currentStrategy && currentAccount) {
      loadInstruments();
    }
  }, [currentStrategy, currentAccount]);

  async function loadInstruments() {
    if (!currentStrategy || !currentAccount) return;

    setLoading(true);
    try {
      const data = await fetchStrategyInstruments(
        currentStrategy.strategy_id,
        currentAccount.trading_account_id
      );
      setInstruments(data);
    } catch (err) {
      console.error('Failed to load instruments:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleRemoveInstrument(instrumentId: number) {
    if (!currentStrategy || !currentAccount) return;
    if (!confirm('Remove this instrument from the strategy?')) return;

    try {
      await removeInstrument(
        currentStrategy.strategy_id,
        instrumentId,
        currentAccount.trading_account_id
      );
      setInstruments((prev) => prev.filter((i) => i.id !== instrumentId));
    } catch (err) {
      console.error('Failed to remove instrument:', err);
      alert('Failed to remove instrument');
    }
  }

  function handleInstrumentAdded(newInstrument: StrategyInstrument) {
    setInstruments((prev) => [...prev, newInstrument]);
    setShowAddModal(false);
  }

  if (!currentStrategy) {
    return <div className={styles.empty}>No strategy selected</div>;
  }

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <h3>Strategy Instruments</h3>
        <button className={styles.addButton} onClick={() => setShowAddModal(true)}>
          + Add Instrument
        </button>
      </div>

      {loading ? (
        <div className={styles.loading}>Loading instruments...</div>
      ) : instruments.length === 0 ? (
        <div className={styles.empty}>
          No instruments in this strategy.
          <br />
          <button onClick={() => setShowAddModal(true)}>Add your first instrument</button>
        </div>
      ) : (
        <div className={styles.tableWrapper}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Type</th>
                <th>Strike</th>
                <th>Direction</th>
                <th>Qty</th>
                <th>Lot Size</th>
                <th>Entry Price</th>
                <th>Current Price</th>
                <th>P&L</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {instruments.map((inst) => (
                <tr key={inst.id}>
                  <td className={styles.symbol}>{inst.tradingsymbol}</td>
                  <td>
                    <span className={styles.badge}>{inst.instrument_type || 'EQ'}</span>
                  </td>
                  <td>{inst.strike ? inst.strike.toFixed(2) : '-'}</td>
                  <td>
                    <span
                      className={
                        inst.direction === 'BUY' ? styles.buyBadge : styles.sellBadge
                      }
                    >
                      {inst.direction}
                    </span>
                  </td>
                  <td>{inst.quantity}</td>
                  <td>{inst.lot_size || 1}</td>
                  <td>₹{inst.entry_price.toFixed(2)}</td>
                  <td>
                    {inst.current_price ? `₹${inst.current_price.toFixed(2)}` : '-'}
                  </td>
                  <td>
                    {inst.current_pnl !== null && inst.current_pnl !== undefined ? (
                      <span
                        className={
                          inst.current_pnl >= 0 ? styles.profitText : styles.lossText
                        }
                      >
                        ₹{inst.current_pnl.toFixed(2)}
                      </span>
                    ) : (
                      '-'
                    )}
                  </td>
                  <td>
                    <button
                      className={styles.removeButton}
                      onClick={() => handleRemoveInstrument(inst.id)}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showAddModal && (
        <AddInstrumentModal
          onClose={() => setShowAddModal(false)}
          onInstrumentAdded={handleInstrumentAdded}
        />
      )}
    </div>
  );
}
```

**File**: `frontend/src/components/tradingDashboard/StrategyInstrumentsPanel.module.css` (new file)

```css
.panel {
  background: var(--surface-color, #1e1e1e);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.addButton {
  padding: 8px 16px;
  background: var(--primary-color, #2196f3);
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.addButton:hover {
  background: var(--primary-hover, #1976d2);
}

.loading,
.empty {
  text-align: center;
  padding: 40px;
  color: var(--text-secondary, #999);
}

.empty button {
  margin-top: 12px;
  padding: 8px 16px;
  background: var(--primary-color, #2196f3);
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.tableWrapper {
  overflow-x: auto;
}

.table {
  width: 100%;
  border-collapse: collapse;
}

.table th,
.table td {
  padding: 12px;
  text-align: left;
  border-bottom: 1px solid var(--border-color, #333);
}

.table th {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary, #999);
  text-transform: uppercase;
}

.table td {
  font-size: 14px;
}

.symbol {
  font-family: 'Courier New', monospace;
  font-weight: 600;
}

.badge {
  display: inline-block;
  padding: 4px 8px;
  background: var(--surface-hover, #2a2a2a);
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.buyBadge {
  display: inline-block;
  padding: 4px 8px;
  background: rgba(76, 175, 80, 0.2);
  color: #4caf50;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.sellBadge {
  display: inline-block;
  padding: 4px 8px;
  background: rgba(244, 67, 54, 0.2);
  color: #f44336;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.profitText {
  color: var(--profit-color, #4caf50);
  font-weight: 600;
}

.lossText {
  color: var(--loss-color, #f44336);
  font-weight: 600;
}

.removeButton {
  padding: 6px 12px;
  background: rgba(244, 67, 54, 0.1);
  color: #f44336;
  border: 1px solid #f44336;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.2s;
}

.removeButton:hover {
  background: rgba(244, 67, 54, 0.2);
}
```

---

### Step 7: Create AddInstrumentModal Component

**File**: `frontend/src/components/tradingDashboard/AddInstrumentModal.tsx` (new file)

```typescript
import React, { useState } from 'react';
import { useStrategy } from '../../contexts/StrategyContext';
import { useTradingAccount } from '../../contexts/TradingAccountContext';
import { StrategyInstrument, AddInstrumentRequest } from '../../types';
import { addInstrument } from '../../services/strategies';
import styles from './AddInstrumentModal.module.css';

interface AddInstrumentModalProps {
  onClose: () => void;
  onInstrumentAdded: (instrument: StrategyInstrument) => void;
}

export default function AddInstrumentModal({
  onClose,
  onInstrumentAdded,
}: AddInstrumentModalProps) {
  const { currentStrategy } = useStrategy();
  const { currentAccount } = useTradingAccount();
  const [tradingsymbol, setTradingsymbol] = useState('');
  const [exchange, setExchange] = useState<'NSE' | 'NFO' | 'BSE'>('NFO');
  const [direction, setDirection] = useState<'BUY' | 'SELL'>('BUY');
  const [quantity, setQuantity] = useState('1');
  const [entryPrice, setEntryPrice] = useState('');
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!currentStrategy || !currentAccount) {
      setError('No strategy or account selected');
      return;
    }

    if (!tradingsymbol.trim() || !entryPrice) {
      setError('Trading symbol and entry price are required');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const data: AddInstrumentRequest = {
        tradingsymbol: tradingsymbol.trim().toUpperCase(),
        exchange,
        direction,
        quantity: parseInt(quantity),
        entry_price: parseFloat(entryPrice),
        notes: notes.trim() || undefined,
      };

      const newInstrument = await addInstrument(
        currentStrategy.strategy_id,
        currentAccount.trading_account_id,
        data
      );

      onInstrumentAdded(newInstrument);
    } catch (err: any) {
      setError(err.message || 'Failed to add instrument');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.header}>
          <h2>Add Instrument</h2>
          <button className={styles.closeButton} onClick={onClose}>
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.row}>
            <div className={styles.field}>
              <label htmlFor="tradingsymbol">Trading Symbol *</label>
              <input
                id="tradingsymbol"
                type="text"
                value={tradingsymbol}
                onChange={(e) => setTradingsymbol(e.target.value)}
                placeholder="e.g., NIFTY25N1123400CE"
                required
                autoFocus
              />
            </div>

            <div className={styles.field}>
              <label htmlFor="exchange">Exchange *</label>
              <select
                id="exchange"
                value={exchange}
                onChange={(e) => setExchange(e.target.value as any)}
                required
              >
                <option value="NFO">NFO</option>
                <option value="NSE">NSE</option>
                <option value="BSE">BSE</option>
              </select>
            </div>
          </div>

          <div className={styles.row}>
            <div className={styles.field}>
              <label htmlFor="direction">Direction *</label>
              <select
                id="direction"
                value={direction}
                onChange={(e) => setDirection(e.target.value as any)}
                required
              >
                <option value="BUY">BUY</option>
                <option value="SELL">SELL</option>
              </select>
            </div>

            <div className={styles.field}>
              <label htmlFor="quantity">Quantity *</label>
              <input
                id="quantity"
                type="number"
                min="1"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                required
              />
            </div>

            <div className={styles.field}>
              <label htmlFor="entry-price">Entry Price (₹) *</label>
              <input
                id="entry-price"
                type="number"
                step="0.05"
                min="0"
                value={entryPrice}
                onChange={(e) => setEntryPrice(e.target.value)}
                placeholder="0.00"
                required
              />
            </div>
          </div>

          <div className={styles.field}>
            <label htmlFor="notes">Notes</label>
            <textarea
              id="notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Optional notes..."
              rows={2}
            />
          </div>

          {error && <div className={styles.error}>{error}</div>}

          <div className={styles.actions}>
            <button type="button" onClick={onClose} disabled={loading}>
              Cancel
            </button>
            <button type="submit" disabled={loading}>
              {loading ? 'Adding...' : 'Add Instrument'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
```

**File**: `frontend/src/components/tradingDashboard/AddInstrumentModal.module.css` (new file)

```css
/* Reuse CreateStrategyModal styles with some additions */
@import './CreateStrategyModal.module.css';

.row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

@media (max-width: 768px) {
  .row {
    grid-template-columns: 1fr;
  }
}

.field select {
  width: 100%;
  padding: 10px 12px;
  background: var(--input-bg, #2a2a2a);
  border: 1px solid var(--border-color, #444);
  border-radius: 4px;
  color: var(--text-primary, #fff);
  font-size: 14px;
  cursor: pointer;
}

.field select:focus {
  outline: none;
  border-color: var(--primary-color, #2196f3);
}
```

---

### Step 8: Create StrategyPnlPanel Component

**File**: `frontend/src/components/tradingDashboard/StrategyPnlPanel.tsx` (new file)

```typescript
import React from 'react';
import { useStrategy } from '../../contexts/StrategyContext';
import styles from './StrategyPnlPanel.module.css';

export default function StrategyPnlPanel() {
  const { currentStrategy } = useStrategy();

  if (!currentStrategy) {
    return null;
  }

  const totalPnl = currentStrategy.total_pnl || 0;
  const currentM2m = currentStrategy.current_m2m || 0;

  return (
    <div className={styles.panel}>
      <h3>Strategy P&L</h3>

      <div className={styles.metrics}>
        <div className={styles.metric}>
          <div className={styles.label}>Current M2M</div>
          <div className={currentM2m >= 0 ? styles.profitValue : styles.lossValue}>
            ₹{currentM2m.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </div>
        </div>

        <div className={styles.metric}>
          <div className={styles.label}>Total P&L</div>
          <div className={totalPnl >= 0 ? styles.profitValue : styles.lossValue}>
            ₹{totalPnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </div>
        </div>

        <div className={styles.metric}>
          <div className={styles.label}>Instrument Count</div>
          <div className={styles.value}>{currentStrategy.instrument_count || 0}</div>
        </div>
      </div>
    </div>
  );
}
```

**File**: `frontend/src/components/tradingDashboard/StrategyPnlPanel.module.css` (new file)

```css
.panel {
  background: var(--surface-color, #1e1e1e);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
}

.panel h3 {
  margin: 0 0 20px 0;
  font-size: 16px;
  font-weight: 600;
}

.metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
}

.metric {
  background: var(--surface-hover, #2a2a2a);
  border-radius: 8px;
  padding: 16px;
}

.label {
  font-size: 12px;
  color: var(--text-secondary, #999);
  text-transform: uppercase;
  font-weight: 600;
  margin-bottom: 8px;
}

.value {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary, #fff);
}

.profitValue {
  font-size: 24px;
  font-weight: 700;
  color: var(--profit-color, #4caf50);
}

.lossValue {
  font-size: 24px;
  font-weight: 700;
  color: var(--loss-color, #f44336);
}
```

---

### Step 9: Create StrategyM2MChart Component

**File**: `frontend/src/components/tradingDashboard/StrategyM2MChart.tsx` (new file)

```typescript
import React, { useState, useEffect } from 'react';
import { useStrategy } from '../../contexts/StrategyContext';
import { useTradingAccount } from '../../contexts/TradingAccountContext';
import { M2MCandle } from '../../types';
import { fetchStrategyM2M } from '../../services/strategies';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import styles from './StrategyM2MChart.module.css';

export default function StrategyM2MChart() {
  const { currentStrategy } = useStrategy();
  const { currentAccount } = useTradingAccount();
  const [candles, setCandles] = useState<M2MCandle[]>([]);
  const [loading, setLoading] = useState(false);
  const [timeRange, setTimeRange] = useState<'1h' | '4h' | '1d' | '7d'>('1d');

  useEffect(() => {
    if (currentStrategy && currentAccount) {
      loadM2MData();
    }
  }, [currentStrategy, currentAccount, timeRange]);

  async function loadM2MData() {
    if (!currentStrategy || !currentAccount) return;

    setLoading(true);
    try {
      const now = new Date();
      const startTime = getStartTime(now, timeRange);

      const data = await fetchStrategyM2M(
        currentStrategy.strategy_id,
        currentAccount.trading_account_id,
        startTime.toISOString(),
        now.toISOString()
      );

      setCandles(data);
    } catch (err) {
      console.error('Failed to load M2M data:', err);
    } finally {
      setLoading(false);
    }
  }

  function getStartTime(now: Date, range: string): Date {
    const start = new Date(now);
    switch (range) {
      case '1h':
        start.setHours(now.getHours() - 1);
        break;
      case '4h':
        start.setHours(now.getHours() - 4);
        break;
      case '1d':
        start.setDate(now.getDate() - 1);
        break;
      case '7d':
        start.setDate(now.getDate() - 7);
        break;
    }
    return start;
  }

  const chartData = candles.map((candle) => ({
    time: new Date(candle.timestamp).toLocaleTimeString('en-IN', {
      hour: '2-digit',
      minute: '2-digit',
    }),
    m2m: parseFloat(candle.close.toString()),
  }));

  if (!currentStrategy) {
    return null;
  }

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <h3>M2M Chart</h3>
        <div className={styles.timeRangeButtons}>
          {(['1h', '4h', '1d', '7d'] as const).map((range) => (
            <button
              key={range}
              className={timeRange === range ? styles.activeButton : ''}
              onClick={() => setTimeRange(range)}
            >
              {range}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className={styles.loading}>Loading chart...</div>
      ) : candles.length === 0 ? (
        <div className={styles.empty}>No M2M data available</div>
      ) : (
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#333" />
            <XAxis dataKey="time" stroke="#999" tick={{ fontSize: 12 }} />
            <YAxis stroke="#999" tick={{ fontSize: 12 }} />
            <Tooltip
              contentStyle={{
                background: '#1e1e1e',
                border: '1px solid #444',
                borderRadius: '4px',
              }}
              labelStyle={{ color: '#999' }}
              itemStyle={{ color: '#fff' }}
            />
            <Line
              type="monotone"
              dataKey="m2m"
              stroke="#2196f3"
              strokeWidth={2}
              dot={false}
              name="M2M (₹)"
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
```

**File**: `frontend/src/components/tradingDashboard/StrategyM2MChart.module.css` (new file)

```css
.panel {
  background: var(--surface-color, #1e1e1e);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.timeRangeButtons {
  display: flex;
  gap: 8px;
}

.timeRangeButtons button {
  padding: 6px 12px;
  background: var(--surface-hover, #2a2a2a);
  color: var(--text-secondary, #999);
  border: 1px solid var(--border-color, #444);
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.timeRangeButtons button:hover {
  background: var(--border-color, #333);
}

.activeButton {
  background: var(--primary-color, #2196f3) !important;
  color: white !important;
  border-color: var(--primary-color, #2196f3) !important;
}

.loading,
.empty {
  text-align: center;
  padding: 80px 20px;
  color: var(--text-secondary, #999);
}
```

---

### Step 10: Integrate into TradingDashboard

**File**: `frontend/src/pages/TradingDashboard.tsx` (modify existing)

```typescript
// Add imports
import { StrategyProvider } from '../contexts/StrategyContext';
import StrategySelector from '../components/tradingDashboard/StrategySelector';
import StrategyInstrumentsPanel from '../components/tradingDashboard/StrategyInstrumentsPanel';
import StrategyPnlPanel from '../components/tradingDashboard/StrategyPnlPanel';
import StrategyM2MChart from '../components/tradingDashboard/StrategyM2MChart';

// Wrap dashboard content with StrategyProvider
export default function TradingDashboard() {
  return (
    <AuthProvider>
      <TradingAccountProvider>
        <StrategyProvider>
          <div className={styles.dashboard}>
            {/* Existing header */}

            {/* Add StrategySelector below account selector */}
            <StrategySelector />

            <div className={styles.content}>
              {/* Add new strategy components */}
              <StrategyPnlPanel />
              <StrategyM2MChart />
              <StrategyInstrumentsPanel />

              {/* Existing components... */}
            </div>
          </div>
        </StrategyProvider>
      </TradingAccountProvider>
    </AuthProvider>
  );
}
```

---

## Success Criteria

- [ ] StrategyContext provides strategies, currentStrategy, CRUD operations
- [ ] StrategySelector dropdown works, shows strategies with instrument count
- [ ] CreateStrategyModal opens, validates, creates new strategy
- [ ] StrategyInstrumentsPanel displays instruments in table format
- [ ] AddInstrumentModal validates, adds instruments with auto-populated metadata
- [ ] StrategyPnlPanel shows current M2M, total P&L, instrument count
- [ ] StrategyM2MChart renders line chart with time range selection
- [ ] All components styled consistently with dark theme
- [ ] Error handling for all API calls
- [ ] Loading states for async operations

---

## Testing Checklist

1. **Strategy Selection**:
   - [ ] Dropdown shows all strategies including default
   - [ ] Selecting strategy updates currentStrategy
   - [ ] Default strategy auto-selected on load

2. **Create Strategy**:
   - [ ] Modal opens/closes correctly
   - [ ] Form validation works (required fields)
   - [ ] New strategy created successfully
   - [ ] New strategy appears in dropdown
   - [ ] New strategy auto-selected after creation

3. **Instruments**:
   - [ ] Instruments table shows all instruments
   - [ ] Add instrument modal validates inputs
   - [ ] New instrument appears in table
   - [ ] Instrument metadata auto-populated (strike, type, lot_size)
   - [ ] Remove instrument confirmation works

4. **P&L Panel**:
   - [ ] Shows current M2M (positive = green, negative = red)
   - [ ] Shows total P&L correctly
   - [ ] Updates when strategy changes

5. **M2M Chart**:
   - [ ] Chart renders with data
   - [ ] Time range buttons work (1h, 4h, 1d, 7d)
   - [ ] Chart updates when time range changes
   - [ ] Tooltip shows M2M value

---

## Estimated Time

**Total**: 6-8 hours (1 full day)

- Step 1-2: Types & Service (1 hour)
- Step 3: StrategyContext (1 hour)
- Step 4-5: StrategySelector & CreateModal (1.5 hours)
- Step 6-7: InstrumentsPanel & AddModal (2 hours)
- Step 8: PnlPanel (0.5 hour)
- Step 9: M2MChart (1.5 hours)
- Step 10: Integration & Testing (1.5 hours)

---

## Next Steps

After Day 3 is complete:
- **Day 4**: Implement Payoff Graphs & Greeks (design already complete)
- **Day 5**: Polish, testing, and final integration

---

## Ready to Implement! 🚀

This prompt provides complete code for all 7 frontend components needed for Day 3. Follow the steps sequentially, test each component, and integrate into the dashboard.
