# KiteConnect Integration: Corrected Implementation Plan

## Architecture Overview

### **Authentication & Access Control Flow** ✅ FULLY IMPLEMENTED (Backend)

```
1. User logs in to Quantagro Platform
   ↓
   POST /api/v1/auth/login (User Service)
   ↓
   Returns JWT access token
   ↓
2. User links Kite trading account
   ↓
   POST /api/v1/trading-accounts/link (User Service)
   Headers: Authorization: Bearer {jwt}
   Body: { broker: "kite", api_key, api_secret, broker_user_id }
   ↓
   Credentials encrypted with KMS, stored in database
   ↓
3. User fetches accessible trading accounts
   ↓
   GET /api/v1/trading-accounts (User Service)
   Headers: Authorization: Bearer {jwt}
   ↓
   Returns:
   - owned_accounts: [] (accounts user owns)
   - shared_accounts: [] (accounts shared with user)
   ↓
4. User selects a trading account to trade with
   ↓
5. Frontend makes trading API calls
   ↓
   POST /orders/place (Ticker Service)
   Headers:
     Authorization: Bearer {jwt}
     X-Account-ID: {trading_account_id}
   ↓
   Ticker Service flow:
   a) Validates JWT with User Service
   b) Calls User Service internal endpoint to get decrypted Kite credentials
   c) Uses credentials to login to Kite (if session expired)
   d) Places order on Kite
   e) Returns result to frontend
```

### **Multi-User, Multi-Account Model** (User Service)

#### Database Schema

**Table: `trading_accounts`**
- Stores encrypted Kite credentials (API key, secret, user ID)
- Each account has ONE owner (user_id)
- Owner has full permissions: `[view, trade, manage]`

**Table: `trading_account_memberships`**
- Enables account sharing between users
- One trading account can have MANY members
- Each member has specific permissions: `[view]`, `[view, trade]`, or `[view, trade, manage]`

#### Example Scenario

```
User Alice (user_id=1):
  - Owns: Kite Account ABC123 (trading_account_id=10)
  - Permissions: [view, trade, manage]
  - Shares with Bob: [view, trade]
  - Shares with Charlie: [view]

User Bob (user_id=2):
  - Owns: Kite Account XYZ789 (trading_account_id=20)
  - Has access to: Alice's ABC123 via membership
  - Permissions on ABC123: [view, trade] (can view & trade, cannot manage)

User Charlie (user_id=3):
  - Has access to: Alice's ABC123 via membership
  - Permissions: [view] (can only view, cannot trade)
```

**API Response for Alice:**
```json
GET /api/v1/trading-accounts
{
  "owned_accounts": [
    {
      "trading_account_id": 10,
      "broker": "kite",
      "broker_user_id": "ABC123",
      "account_name": "My Primary Account",
      "status": "active",
      "is_owner": true,
      "permissions": ["view", "trade", "manage"]
    }
  ],
  "shared_accounts": [],
  "total_accounts": 1
}
```

**API Response for Bob:**
```json
GET /api/v1/trading-accounts
{
  "owned_accounts": [
    {
      "trading_account_id": 20,
      "broker": "kite",
      "broker_user_id": "XYZ789",
      "account_name": "My Account",
      "status": "active",
      "is_owner": true,
      "permissions": ["view", "trade", "manage"]
    }
  ],
  "shared_accounts": [
    {
      "trading_account_id": 10,
      "broker": "kite",
      "broker_user_id": "ABC123",
      "account_name": "Alice's Account",
      "status": "active",
      "is_owner": false,
      "permissions": ["view", "trade"]
    }
  ],
  "total_accounts": 2
}
```

---

## What's Already Implemented ✅

### Backend (100% Complete)

#### User Service
- ✅ User authentication (login, MFA, token refresh)
- ✅ Trading account linking (`POST /api/v1/trading-accounts/link`)
- ✅ Fetch user's accounts (`GET /api/v1/trading-accounts`)
- ✅ KMS-based credential encryption
- ✅ Multi-user membership management
  - `POST /api/v1/trading-accounts/{id}/memberships` - Grant access
  - `DELETE /api/v1/trading-accounts/{id}/memberships/{id}` - Revoke access
  - `GET /api/v1/trading-accounts/{id}/memberships` - List members
- ✅ Permission checking (`POST /api/v1/trading-accounts/{id}/permissions/check`)
- ✅ Internal credential decryption endpoint for Ticker Service

#### Ticker Service
- ✅ Kite session management (auto-login with TOTP)
- ✅ Multi-account orchestration
- ✅ All order APIs (place, modify, cancel, list)
- ✅ Portfolio APIs (positions, holdings)
- ✅ Account APIs (profile, margins)
- ✅ WebSocket market data streaming
- ✅ WebSocket order updates (`ws://ticker-service/advanced/ws/orders/{account_id}`)
- ✅ Order executor with idempotency, retry, circuit breaker

### Frontend (Partially Complete)

#### Already Implemented
- ✅ Login page (`LoginPage.tsx`)
- ✅ Auth context (`AuthContext.tsx`)
- ✅ JWT token management
- ✅ MFA support

#### Missing (What You Need to Build)
- ❌ Trading account linking UI
- ❌ Account selector (switch between owned & shared accounts)
- ❌ Positions panel (currently using mock data)
- ❌ Holdings panel (currently using mock data)
- ❌ Order book panel
- ❌ Funds/margin display
- ❌ Order placement form
- ❌ WebSocket connection for real-time updates
- ❌ Permission-based UI (hide "trade" button if user only has "view" permission)

---

## Implementation Plan

### Phase 1: Account Management UI (2 days)

#### Task 1.1: Fetch and Display Linked Accounts (4 hours)

**Create**: `frontend/src/services/tradingAccounts.ts`
```typescript
import { api } from './api'

const USER_SERVICE_URL = import.meta.env.VITE_USER_SERVICE_URL || 'http://localhost:8002'

export interface TradingAccount {
  trading_account_id: number
  broker: string
  broker_user_id: string
  account_name: string
  status: string
  is_owner: boolean
  permissions: string[] // ["view"], ["view", "trade"], or ["view", "trade", "manage"]
  linked_at: string
  last_used_at: string | null
}

export interface GetTradingAccountsResponse {
  owned_accounts: TradingAccount[]
  shared_accounts: TradingAccount[]
  total_accounts: number
}

export const fetchTradingAccounts = async (jwtToken: string): Promise<GetTradingAccountsResponse> => {
  const response = await fetch(`${USER_SERVICE_URL}/api/v1/trading-accounts`, {
    headers: {
      'Authorization': `Bearer ${jwtToken}`,
      'Content-Type': 'application/json'
    }
  })

  if (!response.ok) {
    throw new Error('Failed to fetch trading accounts')
  }

  return response.json()
}

export const linkTradingAccount = async (
  jwtToken: string,
  accountData: {
    broker: 'kite' | 'upstox' | 'angel' | 'finvasia'
    broker_user_id: string
    api_key: string
    api_secret: string
    access_token?: string
    account_name?: string
  }
) => {
  const response = await fetch(`${USER_SERVICE_URL}/api/v1/trading-accounts/link`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${jwtToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(accountData)
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to link account')
  }

  return response.json()
}
```

**Update**: `frontend/src/components/tradingDashboard/TradingAccountsPanel.tsx`
```typescript
import { useEffect, useState } from 'react'
import { useAuth } from '../../contexts/AuthContext'
import { fetchTradingAccounts, TradingAccount } from '../../services/tradingAccounts'

export const TradingAccountsPanel = () => {
  const { accessToken } = useAuth()
  const [ownedAccounts, setOwnedAccounts] = useState<TradingAccount[]>([])
  const [sharedAccounts, setSharedAccounts] = useState<TradingAccount[]>([])
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!accessToken) return

    const loadAccounts = async () => {
      try {
        setLoading(true)
        const data = await fetchTradingAccounts(accessToken)
        setOwnedAccounts(data.owned_accounts)
        setSharedAccounts(data.shared_accounts)

        // Auto-select first account
        if (data.owned_accounts.length > 0) {
          setSelectedAccountId(data.owned_accounts[0].trading_account_id)
        } else if (data.shared_accounts.length > 0) {
          setSelectedAccountId(data.shared_accounts[0].trading_account_id)
        }
      } catch (err: any) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }

    loadAccounts()
  }, [accessToken])

  const allAccounts = [...ownedAccounts, ...sharedAccounts]
  const selectedAccount = allAccounts.find(acc => acc.trading_account_id === selectedAccountId)

  return (
    <div>
      <h3>Trading Accounts</h3>

      {loading && <p>Loading accounts...</p>}
      {error && <p style={{ color: 'red' }}>{error}</p>}

      {!loading && allAccounts.length === 0 && (
        <div>
          <p>No trading accounts linked.</p>
          <button>Link Kite Account</button>
        </div>
      )}

      {!loading && allAccounts.length > 0 && (
        <>
          <select
            value={selectedAccountId || ''}
            onChange={(e) => setSelectedAccountId(Number(e.target.value))}
          >
            {ownedAccounts.length > 0 && (
              <optgroup label="My Accounts">
                {ownedAccounts.map(acc => (
                  <option key={acc.trading_account_id} value={acc.trading_account_id}>
                    {acc.account_name} ({acc.broker_user_id}) - Owner
                  </option>
                ))}
              </optgroup>
            )}
            {sharedAccounts.length > 0 && (
              <optgroup label="Shared with Me">
                {sharedAccounts.map(acc => (
                  <option key={acc.trading_account_id} value={acc.trading_account_id}>
                    {acc.account_name} ({acc.broker_user_id}) - Shared
                  </option>
                ))}
              </optgroup>
            )}
          </select>

          {selectedAccount && (
            <div>
              <p>Status: {selectedAccount.status}</p>
              <p>Permissions: {selectedAccount.permissions.join(', ')}</p>
              {selectedAccount.is_owner && <span>👑 Owner</span>}
            </div>
          )}
        </>
      )}
    </div>
  )
}
```

#### Task 1.2: Account Linking Modal (6 hours)

**Create**: `frontend/src/components/tradingDashboard/AccountLinkingModal.tsx`
```typescript
import { useState, FormEvent } from 'react'
import { useAuth } from '../../contexts/AuthContext'
import { linkTradingAccount } from '../../services/tradingAccounts'

interface AccountLinkingModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
}

export const AccountLinkingModal = ({ isOpen, onClose, onSuccess }: AccountLinkingModalProps) => {
  const { accessToken } = useAuth()
  const [broker, setBroker] = useState<'kite'>('kite')
  const [brokerUserId, setBrokerUserId] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [apiSecret, setApiSecret] = useState('')
  const [accountName, setAccountName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!accessToken) return

    setLoading(true)
    setError(null)

    try {
      await linkTradingAccount(accessToken, {
        broker,
        broker_user_id: brokerUserId,
        api_key: apiKey,
        api_secret: apiSecret,
        account_name: accountName || `${broker} - ${brokerUserId}`
      })

      onSuccess()
      onClose()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (!isOpen) return null

  return (
    <div style={{ /* modal overlay styles */ }}>
      <div style={{ /* modal content styles */ }}>
        <h2>Link Kite Account</h2>
        <form onSubmit={handleSubmit}>
          {error && <div style={{ color: 'red' }}>{error}</div>}

          <div>
            <label>Account Name (optional)</label>
            <input
              type="text"
              placeholder="My Primary Account"
              value={accountName}
              onChange={(e) => setAccountName(e.target.value)}
            />
          </div>

          <div>
            <label>Kite User ID *</label>
            <input
              type="text"
              placeholder="AB1234"
              value={brokerUserId}
              onChange={(e) => setBrokerUserId(e.target.value)}
              required
            />
          </div>

          <div>
            <label>API Key *</label>
            <input
              type="text"
              placeholder="your_api_key"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              required
            />
          </div>

          <div>
            <label>API Secret *</label>
            <input
              type="password"
              placeholder="your_api_secret"
              value={apiSecret}
              onChange={(e) => setApiSecret(e.target.value)}
              required
            />
          </div>

          <div style={{ marginTop: '20px' }}>
            <button type="submit" disabled={loading}>
              {loading ? 'Linking...' : 'Link Account'}
            </button>
            <button type="button" onClick={onClose}>Cancel</button>
          </div>

          <p style={{ fontSize: '12px', color: '#666', marginTop: '10px' }}>
            Your credentials are encrypted with KMS before storage. Only you can access them.
          </p>
        </form>
      </div>
    </div>
  )
}
```

#### Task 1.3: Create Account Context (2 hours)

**Create**: `frontend/src/contexts/TradingAccountContext.tsx`
```typescript
import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { useAuth } from './AuthContext'
import { fetchTradingAccounts, TradingAccount } from '../services/tradingAccounts'

interface TradingAccountContextType {
  ownedAccounts: TradingAccount[]
  sharedAccounts: TradingAccount[]
  selectedAccount: TradingAccount | null
  selectAccount: (accountId: number) => void
  refreshAccounts: () => Promise<void>
  hasPermission: (permission: 'view' | 'trade' | 'manage') => boolean
  loading: boolean
}

const TradingAccountContext = createContext<TradingAccountContextType | null>(null)

export const TradingAccountProvider = ({ children }: { children: ReactNode }) => {
  const { accessToken } = useAuth()
  const [ownedAccounts, setOwnedAccounts] = useState<TradingAccount[]>([])
  const [sharedAccounts, setSharedAccounts] = useState<TradingAccount[]>([])
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)

  const loadAccounts = async () => {
    if (!accessToken) return

    setLoading(true)
    try {
      const data = await fetchTradingAccounts(accessToken)
      setOwnedAccounts(data.owned_accounts)
      setSharedAccounts(data.shared_accounts)

      // Auto-select first account if none selected
      if (!selectedAccountId) {
        if (data.owned_accounts.length > 0) {
          setSelectedAccountId(data.owned_accounts[0].trading_account_id)
        } else if (data.shared_accounts.length > 0) {
          setSelectedAccountId(data.shared_accounts[0].trading_account_id)
        }
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAccounts()
  }, [accessToken])

  const allAccounts = [...ownedAccounts, ...sharedAccounts]
  const selectedAccount = allAccounts.find(acc => acc.trading_account_id === selectedAccountId) || null

  const hasPermission = (permission: 'view' | 'trade' | 'manage'): boolean => {
    if (!selectedAccount) return false
    return selectedAccount.permissions.includes(permission)
  }

  return (
    <TradingAccountContext.Provider
      value={{
        ownedAccounts,
        sharedAccounts,
        selectedAccount,
        selectAccount: setSelectedAccountId,
        refreshAccounts: loadAccounts,
        hasPermission,
        loading
      }}
    >
      {children}
    </TradingAccountContext.Provider>
  )
}

export const useTradingAccount = () => {
  const context = useContext(TradingAccountContext)
  if (!context) {
    throw new Error('useTradingAccount must be used within TradingAccountProvider')
  }
  return context
}
```

---

### Phase 2: Portfolio Display (3 days)

#### Task 2.1: Positions Panel (8 hours)

**Create**: `frontend/src/services/portfolio.ts`
```typescript
import { api } from './api'

const TICKER_SERVICE_URL = import.meta.env.VITE_TICKER_SERVICE_URL || 'http://localhost:8001'

export interface Position {
  tradingsymbol: string
  exchange: string
  product: string
  quantity: number
  average_price: number
  last_price: number
  pnl: number
  m2m: number
  value: number
  buy_quantity: number
  buy_price: number
  sell_quantity: number
  sell_price: number
}

export const fetchPositions = async (jwtToken: string, tradingAccountId: number) => {
  const response = await fetch(`${TICKER_SERVICE_URL}/portfolio/positions`, {
    headers: {
      'Authorization': `Bearer ${jwtToken}`,
      'X-Account-ID': String(tradingAccountId)
    }
  })

  if (!response.ok) {
    throw new Error('Failed to fetch positions')
  }

  const data = await response.json()
  return data // { net: Position[], day: Position[] }
}

export const fetchHoldings = async (jwtToken: string, tradingAccountId: number) => {
  const response = await fetch(`${TICKER_SERVICE_URL}/portfolio/holdings`, {
    headers: {
      'Authorization': `Bearer ${jwtToken}`,
      'X-Account-ID': String(tradingAccountId)
    }
  })

  if (!response.ok) {
    throw new Error('Failed to fetch holdings')
  }

  return response.json()
}

export const fetchMargins = async (jwtToken: string, tradingAccountId: number) => {
  const response = await fetch(`${TICKER_SERVICE_URL}/account/margins`, {
    headers: {
      'Authorization': `Bearer ${jwtToken}`,
      'X-Account-ID': String(tradingAccountId)
    }
  })

  if (!response.ok) {
    throw new Error('Failed to fetch margins')
  }

  return response.json()
}
```

**Create**: `frontend/src/components/tradingDashboard/PositionsPanel.tsx`
```typescript
import { useEffect, useState } from 'react'
import { useAuth } from '../../contexts/AuthContext'
import { useTradingAccount } from '../../contexts/TradingAccountContext'
import { fetchPositions, Position } from '../../services/portfolio'

export const PositionsPanel = () => {
  const { accessToken } = useAuth()
  const { selectedAccount } = useTradingAccount()
  const [netPositions, setNetPositions] = useState<Position[]>([])
  const [dayPositions, setDayPositions] = useState<Position[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!accessToken || !selectedAccount) return

    const loadPositions = async () => {
      try {
        setLoading(true)
        const data = await fetchPositions(accessToken, selectedAccount.trading_account_id)
        setNetPositions(data.net || [])
        setDayPositions(data.day || [])
        setError(null)
      } catch (err: any) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }

    loadPositions()

    // Poll every 5 seconds for real-time updates
    const interval = setInterval(loadPositions, 5000)
    return () => clearInterval(interval)
  }, [accessToken, selectedAccount?.trading_account_id])

  if (loading) return <div>Loading positions...</div>
  if (error) return <div style={{ color: 'red' }}>Error: {error}</div>
  if (netPositions.length === 0) return <div>No open positions</div>

  return (
    <div>
      <h3>Net Positions</h3>
      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Qty</th>
            <th>Avg Price</th>
            <th>LTP</th>
            <th>P&L</th>
            <th>M2M</th>
          </tr>
        </thead>
        <tbody>
          {netPositions.map((pos, idx) => (
            <tr key={idx}>
              <td>{pos.tradingsymbol}</td>
              <td>{pos.quantity}</td>
              <td>{pos.average_price.toFixed(2)}</td>
              <td>{pos.last_price.toFixed(2)}</td>
              <td style={{ color: pos.pnl >= 0 ? 'green' : 'red' }}>
                {pos.pnl.toFixed(2)}
              </td>
              <td style={{ color: pos.m2m >= 0 ? 'green' : 'red' }}>
                {pos.m2m.toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

#### Task 2.2: Holdings Panel (6 hours) - Similar structure to Positions

#### Task 2.3: Funds/Margin Panel (4 hours) - Display available cash, used margin, etc.

---

### Phase 3: Order Management (4.5 days)

#### Task 3.1: Orders Service & Order Book Panel (8 hours)

**Create**: `frontend/src/services/orders.ts`
```typescript
const TICKER_SERVICE_URL = import.meta.env.VITE_TICKER_SERVICE_URL || 'http://localhost:8001'

export const fetchOrders = async (jwtToken: string, tradingAccountId: number) => {
  const response = await fetch(`${TICKER_SERVICE_URL}/orders/`, {
    headers: {
      'Authorization': `Bearer ${jwtToken}`,
      'X-Account-ID': String(tradingAccountId)
    }
  })

  if (!response.ok) {
    throw new Error('Failed to fetch orders')
  }

  return response.json()
}

export const placeOrder = async (
  jwtToken: string,
  tradingAccountId: number,
  orderParams: {
    tradingsymbol: string
    exchange: string
    transaction_type: 'BUY' | 'SELL'
    order_type: 'MARKET' | 'LIMIT' | 'SL' | 'SL-M'
    product: 'CNC' | 'MIS' | 'NRML'
    quantity: number
    price?: number
    trigger_price?: number
    validity?: 'DAY' | 'IOC'
  }
) => {
  const response = await fetch(`${TICKER_SERVICE_URL}/orders/place`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${jwtToken}`,
      'X-Account-ID': String(tradingAccountId),
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(orderParams)
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to place order')
  }

  return response.json() // { task_id, status }
}

export const cancelOrder = async (
  jwtToken: string,
  tradingAccountId: number,
  orderId: string
) => {
  const response = await fetch(`${TICKER_SERVICE_URL}/orders/cancel`, {
    method: 'DELETE',
    headers: {
      'Authorization': `Bearer ${jwtToken}`,
      'X-Account-ID': String(tradingAccountId)
    },
    body: JSON.stringify({ order_id: orderId })
  })

  if (!response.ok) {
    throw new Error('Failed to cancel order')
  }

  return response.json()
}
```

#### Task 3.2: Order Placement Modal (12 hours)

**Create**: `frontend/src/components/tradingDashboard/OrderPlacementModal.tsx`
- Form with fields: symbol, exchange, buy/sell, order type, quantity, price
- Form validation (lot size, tick size, trigger price logic)
- Submit order and show task status
- Poll task status endpoint until COMPLETED/FAILED

#### Task 3.3: Order Book Display (4 hours)

**Create**: `frontend/src/components/tradingDashboard/OrderBookPanel.tsx`
- Display all orders with status colors
- Add cancel button (only for PENDING orders)
- Show order details on click
- Auto-refresh every 3 seconds

#### Task 3.4: Permission-Based UI (4 hours)

**Update all components to check permissions:**
```typescript
const { hasPermission } = useTradingAccount()

// In OrderPlacementModal
{hasPermission('trade') && (
  <button>Place Order</button>
)}

// In PositionsPanel
{hasPermission('trade') && (
  <button>Square Off</button>
)}
```

---

### Phase 4: Real-time Updates (3 days)

#### Task 4.1: WebSocket Connection (6 hours)

**Create**: `frontend/src/services/ordersWebSocket.ts`
```typescript
const TICKER_WS_URL = import.meta.env.VITE_TICKER_WS_URL || 'ws://localhost:8001'

export const connectOrdersWebSocket = (
  jwtToken: string,
  tradingAccountId: number,
  onUpdate: (update: any) => void
) => {
  const ws = new WebSocket(
    `${TICKER_WS_URL}/advanced/ws/orders/${tradingAccountId}?token=${jwtToken}`
  )

  ws.onopen = () => {
    console.log('WebSocket connected')
  }

  ws.onmessage = (event) => {
    const update = JSON.parse(event.data)
    onUpdate(update)
  }

  ws.onerror = (error) => {
    console.error('WebSocket error:', error)
  }

  ws.onclose = () => {
    console.log('WebSocket closed, reconnecting in 5s...')
    setTimeout(() => connectOrdersWebSocket(jwtToken, tradingAccountId, onUpdate), 5000)
  }

  // Heartbeat every 30 seconds
  const heartbeat = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'ping' }))
    }
  }, 30000)

  return () => {
    clearInterval(heartbeat)
    ws.close()
  }
}
```

#### Task 4.2: Integrate WebSocket in Dashboard (4 hours)

**Update**: `frontend/src/pages/TradingDashboard.tsx`
```typescript
useEffect(() => {
  if (!accessToken || !selectedAccount) return

  const cleanup = connectOrdersWebSocket(
    accessToken,
    selectedAccount.trading_account_id,
    (update) => {
      if (update.type === 'order_update') {
        // Refresh orders list
        queryClient.invalidateQueries(['orders'])
      }
      if (update.type === 'task_update') {
        // Update task status
        console.log('Task update:', update)
      }
    }
  )

  return cleanup
}, [accessToken, selectedAccount?.trading_account_id])
```

#### Task 4.3: Toast Notifications (4 hours)

- Install toast library (react-hot-toast or similar)
- Show notifications for:
  - Order filled
  - Order rejected
  - Position squared off
  - Account switched

---

### Phase 5: Advanced Features (3 days)

- GTT UI
- Basket orders
- Trade history panel
- Account sharing UI (grant/revoke access)

---

## Environment Variables

**Frontend** (`.env`):
```env
VITE_USER_SERVICE_URL=http://localhost:8002
VITE_TICKER_SERVICE_URL=http://localhost:8001
VITE_TICKER_WS_URL=ws://localhost:8001
```

---

## Testing Checklist

### Phase 1
- [ ] User can log in with credentials
- [ ] User can link Kite account
- [ ] Linked accounts appear in list
- [ ] User can switch between owned and shared accounts
- [ ] Shared accounts show correct permissions

### Phase 2
- [ ] Positions display matches Kite app
- [ ] Holdings display matches Kite app
- [ ] Margins/funds are accurate
- [ ] Auto-refresh works (5-10 seconds)

### Phase 3
- [ ] Order book displays correctly
- [ ] User with "trade" permission can place order
- [ ] User with only "view" permission cannot place order
- [ ] Order placement shows task status
- [ ] Order cancellation works

### Phase 4
- [ ] WebSocket connects successfully
- [ ] Order status updates in real-time
- [ ] Positions update when order fills
- [ ] Reconnection works after disconnect

---

## Total Timeline

| Phase | Duration | What You're Building |
|-------|----------|---------------------|
| Phase 1 | 2 days | Account linking & selector UI |
| Phase 2 | 3 days | Positions, holdings, funds panels |
| Phase 3 | 4.5 days | Order book, placement form, permissions |
| Phase 4 | 3 days | WebSocket real-time updates |
| Phase 5 | 3 days | Advanced features (optional) |
| **Total** | **15.5 days** | Full KiteConnect integration |

---

## Key Takeaway

✅ **User Service handles ALL authentication and access control**
✅ **Ticker Service handles ALL Kite API calls**
✅ **Frontend just needs to connect the UI to these existing services**

**No backend changes needed. Only frontend work required.**
