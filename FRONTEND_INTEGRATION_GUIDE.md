# Frontend Integration Guide for Alert Service

## Overview

The frontend uses a **service-based architecture** with Axios HTTP client and WebSocket connections for real-time data. This guide documents the current patterns and how to integrate the Alert Service following the same patterns.

---

## Current Architecture

### 1. API Client Setup

**Location:** `/mnt/stocksblitz-data/Quantagro/tradingview-viz/frontend/src/services/api.ts`

The frontend uses a centralized Axios instance:

```typescript
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/tradingview-api'

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000, // 2 minutes
  headers: {
    'Content-Type': 'application/json'
  }
})
```

**Key Points:**
- Base URL from environment: `VITE_API_BASE_URL`
- 120-second timeout (for slow operations)
- JSON content-type default
- All services import this single axios instance

**Environment Variables:**
```bash
VITE_API_BASE_URL      # Base URL for backend API (default: '/tradingview-api')
VITE_CHART_SYMBOL      # Default chart symbol
VITE_MONITOR_SYMBOL    # Default monitor symbol
VITE_API_URL           # Used for replay service specifically
```

---

## Service Integration Patterns

### Pattern 1: REST API with Axios

**Location:** `/mnt/stocksblitz-data/Quantagro/tradingview-viz/frontend/src/services/trading.ts`

All services follow this pattern:

```typescript
import { api } from './api'

const API_BASE = '/accounts'  // Endpoint prefix

// Define TypeScript interfaces for responses
export interface TradingAccount {
  id: string
  display_name: string
  user_id: string
  combined_pnl: number
  margin_used: number
  available_margin: number
  roi_percent: number
  has_exposure: boolean
}

// API functions
export const fetchAllAccounts = async (): Promise<TradingAccount[]> => {
  try {
    const response = await api.get(API_BASE)
    const data = response.data

    if (data.status === 'success' && data.accounts) {
      return data.accounts.map(mapBackendAccount)
    }

    console.error('Failed to fetch accounts:', data)
    return []
  } catch (error) {
    console.error('Error fetching accounts:', error)
    return []
  }
}

// GET with parameters
export const fetchAccountOrders = async (
  accountId: string,
  underlying?: string
): Promise<Order[]> => {
  try {
    const response = await api.get(`${API_BASE}/${accountId}/orders`)
    const data = response.data

    if (data.status === 'success' && data.orders) {
      return data.orders.map(mapOrder)
    }

    return []
  } catch (error) {
    console.error(`Error fetching orders for account ${accountId}:`, error)
    return []
  }
}

// POST request
export const createLabel = async (label: LabelCreateRequest): Promise<LabelResponse> => {
  const response = await api.post<LabelResponse>('/api/labels', label)
  return response.data
}

// PATCH request
export const updateLabel = async (labelId: string, updates: LabelUpdateRequest): Promise<LabelResponse> => {
  const response = await api.patch<LabelResponse>(`/api/labels/${labelId}`, updates)
  return response.data
}

// DELETE request with body
export const deleteLabel = async (labelId: string, symbol: string, timeframe: string, timestamp: number): Promise<LabelResponse> => {
  const response = await api.delete<LabelResponse>('/api/labels', { 
    data: { id: labelId, symbol, timeframe, timestamp } 
  })
  return response.data
}
```

**Best Practices:**
1. Always define TypeScript interfaces for responses
2. Use try-catch for error handling
3. Log errors to console for debugging
4. Return sensible defaults (empty arrays, null, etc.) instead of throwing
5. Check response status and data structure before using
6. Map backend response to frontend models

---

### Pattern 2: WebSocket Real-Time Data

**Location:** `/mnt/stocksblitz-data/Quantagro/tradingview-viz/frontend/src/services/labels.ts`

WebSocket patterns are used for real-time data:

```typescript
// Build WebSocket URL intelligently
const buildLabelsWsUrl = (): string => {
  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/tradingview-api'
  const base = API_BASE_URL
  
  // Check if absolute URL (http://host or https://host)
  const isAbsolute = base.startsWith('http://') || base.startsWith('https://')
  
  let wsUrl: string
  if (isAbsolute) {
    // Replace http/https with ws/wss
    const protocol = base.startsWith('https://') ? 'wss:' : 'ws:'
    wsUrl = base.replace(/^https?:/, protocol)
  } else {
    // Relative URL - construct based on current location
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    wsUrl = `${protocol}//${host}${base}`
  }
  
  // Add the stream endpoint
  return `${wsUrl}/labels/stream`
}

// Create WebSocket connection
export const connectLabelStream = (): WebSocket => {
  const wsUrl = buildLabelsWsUrl()
  return new WebSocket(wsUrl)
}

// Subscribe to specific data
export const subscribeLabelStream = (
  ws: WebSocket, 
  symbol: string, 
  timeframe: string
): void => {
  if (ws.readyState === WebSocket.OPEN) {
    const message: LabelSubscribeMessage = {
      action: 'subscribe',
      channel: 'labels',
      symbol,
      timeframe
    }
    ws.send(JSON.stringify(message))
  }
}

// Parse incoming messages
export const parseLabelMessage = (data: string): LabelDeltaWSPayload | null => {
  try {
    const message = JSON.parse(data)
    if (message.type && message.type.startsWith('label.')) {
      return message as LabelDeltaWSPayload
    }
    return null
  } catch (error) {
    console.error('Failed to parse label message:', error)
    return null
  }
}
```

**WebSocket Client Class Pattern:**

```typescript
export class ReplayWebSocketClient {
  private ws: WebSocket | null = null
  private messageHandler: ((data: any) => void) | null = null
  private reconnectTimeout: number | null = null

  constructor(private url: string) {}

  connect(onMessage: (data: any) => void) {
    this.messageHandler = onMessage
    this.ws = new WebSocket(this.url)

    this.ws.onopen = () => {
      console.log('[Replay WS] Connected')
    }

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        this.messageHandler?.(data)
      } catch (err) {
        console.error('[Replay WS] Parse error:', err)
      }
    }

    this.ws.onerror = (error) => {
      console.error('[Replay WS] Error:', error)
    }

    this.ws.onclose = () => {
      console.log('[Replay WS] Disconnected')
      // Auto-reconnect after 3s
      this.reconnectTimeout = window.setTimeout(() => {
        this.connect(onMessage)
      }, 3000)
    }
  }

  send(message: any) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message))
    }
  }

  disconnect() {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout)
    }
    this.ws?.close()
    this.ws = null
  }
}
```

---

## Error Handling Patterns

### 1. Service-Level Error Handling

```typescript
// Pattern 1: Graceful degradation (return defaults)
export const fetchAllAccounts = async (): Promise<TradingAccount[]> => {
  try {
    const response = await api.get(API_BASE)
    if (data.status === 'success' && data.accounts) {
      return data.accounts.map(mapBackendAccount)
    }
    console.error('Failed to fetch accounts:', data)
    return []  // Return empty array instead of throwing
  } catch (error) {
    console.error('Error fetching accounts:', error)
    return []
  }
}

// Pattern 2: Throw for critical failures
export const fetchAccountFunds = async (accountId: string): Promise<Funds> => {
  try {
    const response = await api.get(`${API_BASE}/${accountId}/funds`)
    if (data.status === 'success' && data.funds) {
      return mapFunds(data.funds)
    }
    return defaultFunds(accountId)
  } catch (error) {
    console.error(`Error fetching funds for account ${accountId}:`, error)
    throw new Error(`Failed to fetch funds for account ${accountId}`)
  }
}
```

### 2. Component-Level Error Handling

```typescript
// Error Boundary Component
export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary">
          <h2>Component Error</h2>
          <p>Something went wrong in this component.</p>
          <button onClick={() => this.setState({ hasError: false })}>
            Try Again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
```

### 3. Hook-Level Error Handling with try-catch

```typescript
const fetchData = async () => {
  try {
    const [h, c] = await Promise.all([
      fetchHealth(),
      fetchCacheStats()
    ])
    setHealth(h)
    setCacheStats(c)
  } catch (e) {
    // Silently handle or log non-critical errors
    console.error('Failed to fetch health data:', e)
  }
}
```

---

## TypeScript Types

### Response Types

```typescript
// Location: frontend/src/types.ts

export interface HealthStatus {
  status: string
  database: string
  redis: string
  cache_stats: CacheStats
  uptime: number
  version: string
}

export interface CacheStats {
  l1_hits: number
  l2_hits: number
  l3_hits: number
  total_misses: number
  hit_rate: number
  memory_cache_size: number
  redis_keys: number
}

// API Response envelope
export interface ApiResponse<T> {
  status: 'success' | 'error'
  data?: T
  message?: string
  error?: string
}
```

---

## How Services Are Used in Components

### Pattern 1: useEffect for Data Loading

```typescript
// Location: frontend/src/pages/MonitorPage.tsx

const MonitorPage: React.FC = () => {
  const [accounts, setAccounts] = useState<TradingAccount[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const loadAccounts = async () => {
      setLoading(true)
      try {
        const allAccounts = await fetchAllAccounts()
        setAccounts(allAccounts)
      } finally {
        setLoading(false)
      }
    }
    
    loadAccounts()
  }, []) // Run once on mount

  return (
    <div>
      {loading ? (
        <p>Loading...</p>
      ) : (
        <TradingAccountsPanel accounts={accounts} />
      )}
    </div>
  )
}
```

### Pattern 2: WebSocket Integration

```typescript
// Location: frontend/src/components/nifty-monitor/MonitorSyncContext.tsx

useEffect(() => {
  const ws = connectMonitorStream()
  
  const handleMessage = (event: MessageEvent) => {
    try {
      const message: MonitorStreamMessage = JSON.parse(event.data)
      // Process real-time data
      handleStreamMessage(message)
    } catch (error) {
      console.error('Failed to process message:', error)
    }
  }

  ws.addEventListener('message', handleMessage)

  return () => {
    ws.removeEventListener('message', handleMessage)
    ws.close()
  }
}, [])
```

---

## How to Integrate Alert Service

### Step 1: Create Alert Service

**File:** `/mnt/stocksblitz-data/Quantagro/tradingview-viz/frontend/src/services/alerts.ts`

```typescript
import { api } from './api'

const API_BASE = '/alerts'

// Define types matching alert service API
export interface Alert {
  id: string
  name: string
  alert_type: 'price' | 'indicator' | 'volume'
  priority: 'low' | 'medium' | 'high'
  symbol: string
  condition_config: Record<string, any>
  notification_channels: string[]
  is_active: boolean
  created_at: string
  triggered_count: number
}

export interface AlertCreate {
  name: string
  alert_type: string
  priority: string
  condition_config: Record<string, any>
  notification_channels: string[]
}

export interface AlertUpdate {
  name?: string
  priority?: string
  is_active?: boolean
  condition_config?: Record<string, any>
  notification_channels?: string[]
}

// CRUD Operations
export const createAlert = async (alert: AlertCreate): Promise<Alert> => {
  try {
    const response = await api.post<Alert>(`${API_BASE}`, alert)
    return response.data
  } catch (error) {
    console.error('Error creating alert:', error)
    throw error
  }
}

export const fetchAlerts = async (): Promise<Alert[]> => {
  try {
    const response = await api.get<{ alerts: Alert[] }>(`${API_BASE}`)
    return response.data.alerts || []
  } catch (error) {
    console.error('Error fetching alerts:', error)
    return []
  }
}

export const fetchAlert = async (alertId: string): Promise<Alert | null> => {
  try {
    const response = await api.get<Alert>(`${API_BASE}/${alertId}`)
    return response.data
  } catch (error) {
    console.error(`Error fetching alert ${alertId}:`, error)
    return null
  }
}

export const updateAlert = async (alertId: string, updates: AlertUpdate): Promise<Alert> => {
  try {
    const response = await api.patch<Alert>(`${API_BASE}/${alertId}`, updates)
    return response.data
  } catch (error) {
    console.error(`Error updating alert ${alertId}:`, error)
    throw error
  }
}

export const deleteAlert = async (alertId: string): Promise<void> => {
  try {
    await api.delete(`${API_BASE}/${alertId}`)
  } catch (error) {
    console.error(`Error deleting alert ${alertId}:`, error)
    throw error
  }
}

export const toggleAlert = async (alertId: string, isActive: boolean): Promise<Alert> => {
  return updateAlert(alertId, { is_active: isActive })
}

// WebSocket for real-time alert triggers
const buildAlertsWsUrl = (): string => {
  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/tradingview-api'
  const base = API_BASE_URL
  const isAbsolute = base.startsWith('http://') || base.startsWith('https://')
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  
  if (isAbsolute) {
    const url = new URL(base)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    url.pathname = `${url.pathname.replace(/\/$/, '')}/alerts/stream`
    return url.toString()
  }
  return `${protocol}//${window.location.host}${base.replace(/\/$/, '')}/alerts/stream`
}

export const connectAlertStream = (): WebSocket => {
  const wsUrl = buildAlertsWsUrl()
  return new WebSocket(wsUrl)
}

export interface AlertTriggerMessage {
  type: 'alert_triggered'
  alert_id: string
  alert_name: string
  timestamp: string
  triggered_value: number
  condition_value: number
}

export const parseAlertMessage = (data: string): AlertTriggerMessage | null => {
  try {
    const message = JSON.parse(data)
    if (message.type === 'alert_triggered') {
      return message as AlertTriggerMessage
    }
    return null
  } catch (error) {
    console.error('Failed to parse alert message:', error)
    return null
  }
}
```

### Step 2: Create Alert Context

**File:** `/mnt/stocksblitz-data/Quantagro/tradingview-viz/frontend/src/context/AlertContext.tsx`

```typescript
import React, { createContext, useContext, useState, useEffect } from 'react'
import { Alert, connectAlertStream, parseAlertMessage, AlertTriggerMessage } from '../services/alerts'

interface AlertContextType {
  alerts: Alert[]
  triggeredAlerts: AlertTriggerMessage[]
  loading: boolean
  error: string | null
  addAlert: (alert: Alert) => void
  removeAlert: (alertId: string) => void
  clearTriggers: () => void
}

const AlertContext = createContext<AlertContextType | undefined>(undefined)

export const AlertProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [triggeredAlerts, setTriggeredAlerts] = useState<AlertTriggerMessage[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const ws = connectAlertStream()

    ws.onmessage = (event) => {
      const message = parseAlertMessage(event.data)
      if (message) {
        setTriggeredAlerts(prev => [message, ...prev])
      }
    }

    ws.onerror = () => {
      setError('WebSocket connection failed')
    }

    return () => {
      ws.close()
    }
  }, [])

  const addAlert = (alert: Alert) => {
    setAlerts(prev => [alert, ...prev])
  }

  const removeAlert = (alertId: string) => {
    setAlerts(prev => prev.filter(a => a.id !== alertId))
  }

  const clearTriggers = () => {
    setTriggeredAlerts([])
  }

  return (
    <AlertContext.Provider value={{ alerts, triggeredAlerts, loading, error, addAlert, removeAlert, clearTriggers }}>
      {children}
    </AlertContext.Provider>
  )
}

export const useAlerts = () => {
  const context = useContext(AlertContext)
  if (!context) {
    throw new Error('useAlerts must be used within AlertProvider')
  }
  return context
}
```

### Step 3: Create Alert Management Component

**File:** `/mnt/stocksblitz-data/Quantagro/tradingview-viz/frontend/src/components/AlertPanel.tsx`

```typescript
import React, { useEffect, useState } from 'react'
import { fetchAlerts, createAlert, updateAlert, deleteAlert } from '../services/alerts'
import { useAlerts } from '../context/AlertContext'
import type { Alert, AlertCreate } from '../services/alerts'

const AlertPanel: React.FC = () => {
  const { alerts, triggeredAlerts, clearTriggers } = useAlerts()
  const [loading, setLoading] = useState(false)
  const [showForm, setShowForm] = useState(false)

  useEffect(() => {
    loadAlerts()
  }, [])

  const loadAlerts = async () => {
    setLoading(true)
    try {
      const data = await fetchAlerts()
      // Update context if needed
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async (alertData: AlertCreate) => {
    try {
      const newAlert = await createAlert(alertData)
      console.log('Alert created:', newAlert)
      setShowForm(false)
      loadAlerts()
    } catch (error) {
      console.error('Failed to create alert:', error)
    }
  }

  const handleToggle = async (alertId: string, isActive: boolean) => {
    try {
      await updateAlert(alertId, { is_active: !isActive })
      loadAlerts()
    } catch (error) {
      console.error('Failed to toggle alert:', error)
    }
  }

  const handleDelete = async (alertId: string) => {
    try {
      await deleteAlert(alertId)
      loadAlerts()
    } catch (error) {
      console.error('Failed to delete alert:', error)
    }
  }

  return (
    <div className="alert-panel">
      <div className="alert-panel__header">
        <h3>Alerts ({alerts.length})</h3>
        <button onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancel' : 'New Alert'}
        </button>
      </div>

      {triggeredAlerts.length > 0 && (
        <div className="alert-panel__triggered">
          <h4>Triggered Alerts ({triggeredAlerts.length})</h4>
          <ul>
            {triggeredAlerts.map(alert => (
              <li key={`${alert.alert_id}-${alert.timestamp}`}>
                {alert.alert_name}: {alert.triggered_value}
              </li>
            ))}
          </ul>
          <button onClick={clearTriggers}>Clear</button>
        </div>
      )}

      {showForm && (
        <AlertForm onSubmit={handleCreate} onCancel={() => setShowForm(false)} />
      )}

      {loading ? (
        <p>Loading alerts...</p>
      ) : (
        <div className="alert-panel__list">
          {alerts.map(alert => (
            <AlertItem
              key={alert.id}
              alert={alert}
              onToggle={handleToggle}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export default AlertPanel
```

### Step 4: Add to Main App

```typescript
// frontend/src/pages/MonitorPage.tsx

import AlertPanel from '../components/AlertPanel'
import { AlertProvider } from '../context/AlertContext'

export const MonitorPage: React.FC = () => {
  return (
    <AlertProvider>
      <div className="monitor-page">
        <AlertPanel />
        {/* ... rest of monitor page ... */}
      </div>
    </AlertProvider>
  )
}
```

---

## Vite Configuration for Alert Service Proxy

**File:** `frontend/vite.config.ts`

Add proxy for alert service:

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 3002,
    proxy: {
      // Existing proxies
      '/api': {
        target: 'http://127.0.0.1:8081',
        changeOrigin: true,
      },
      '/alerts': {
        target: 'http://127.0.0.1:8090',  // Alert service port
        changeOrigin: true,
        ws: true,  // Enable WebSocket
      },
    },
  },
})
```

---

## Summary of Integration Steps

1. **Create Alert Service** (`/frontend/src/services/alerts.ts`)
   - Define TypeScript interfaces
   - Implement CRUD operations using shared `api` client
   - Add WebSocket utilities

2. **Create Alert Context** (`/frontend/src/context/AlertContext.tsx`)
   - Provide global state for alerts
   - Manage WebSocket subscriptions
   - Handle triggered alerts

3. **Create Alert Components** (`/frontend/src/components/AlertPanel.tsx`)
   - Display alerts list
   - Show triggered alerts
   - Create/edit/delete alerts

4. **Update Vite Config**
   - Add proxy for `/alerts` endpoint

5. **Wrap App with AlertProvider**
   - Use in main pages or globally

---

## Key Differences from Other Services

| Aspect | Labels Service | Trading Service | Alert Service |
|--------|---|---|---|
| **Base URL** | `/api` | `/accounts` | `/alerts` |
| **WebSocket** | Yes (`/labels/stream`) | No (WIP) | Yes (`/alerts/stream`) |
| **Response Format** | `{ labels: Label[] }` | `{ status, accounts }` | `{ status, alerts }` |
| **Error Handling** | Graceful degradation | Graceful degradation | Throws for critical |
| **Real-time** | Required | Not yet | Required |

---

## Recommended Reading

- **Service Pattern:** `frontend/src/services/trading.ts`
- **WebSocket Pattern:** `frontend/src/services/labels.ts`
- **Component Usage:** `frontend/src/pages/MonitorPage.tsx`
- **Error Handling:** `frontend/src/components/ErrorBoundary.tsx`

