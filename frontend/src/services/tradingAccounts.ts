/**
 * Trading Accounts Service
 *
 * Handles communication with User Service for trading account management:
 * - Fetch user's owned and shared accounts
 * - Link new broker accounts
 * - Manage account memberships
 */

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

export interface LinkAccountRequest {
  broker: 'kite' | 'upstox' | 'angel' | 'finvasia'
  broker_user_id: string
  api_key: string
  api_secret: string
  password: string
  totp_seed: string
  access_token?: string
  account_name?: string
}

export interface LinkAccountResponse {
  trading_account_id: number
  status: string
}

/**
 * Fetch all trading accounts accessible by the current user
 * Returns both owned accounts and accounts shared via memberships
 */
export const fetchTradingAccounts = async (jwtToken: string): Promise<GetTradingAccountsResponse> => {
  const response = await fetch(`${USER_SERVICE_URL}/api/v1/trading-accounts`, {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${jwtToken}`,
      'Content-Type': 'application/json'
    }
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to fetch trading accounts' }))
    throw new Error(error.detail || 'Failed to fetch trading accounts')
  }

  return response.json()
}

/**
 * Link a new broker trading account to the user's profile
 * Credentials are encrypted with KMS before storage
 */
export const linkTradingAccount = async (
  jwtToken: string,
  accountData: LinkAccountRequest
): Promise<LinkAccountResponse> => {
  const response = await fetch(`${USER_SERVICE_URL}/api/v1/trading-accounts/link`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${jwtToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(accountData)
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to link account' }))
    throw new Error(error.detail || 'Failed to link account')
  }

  return response.json()
}

/**
 * Unlink a trading account
 * Only the owner can unlink an account
 */
export const unlinkTradingAccount = async (
  jwtToken: string,
  tradingAccountId: number
): Promise<void> => {
  const response = await fetch(`${USER_SERVICE_URL}/api/v1/trading-accounts/${tradingAccountId}`, {
    method: 'DELETE',
    headers: {
      'Authorization': `Bearer ${jwtToken}`,
      'Content-Type': 'application/json'
    }
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to unlink account' }))
    throw new Error(error.detail || 'Failed to unlink account')
  }
}

/**
 * Get friendly permission labels
 */
export const getPermissionLabel = (permissions: string[]): string => {
  if (permissions.includes('manage')) return 'Full Access'
  if (permissions.includes('trade')) return 'View & Trade'
  if (permissions.includes('view')) return 'View Only'
  return 'No Access'
}

/**
 * Check if user has specific permission
 */
export const hasPermission = (account: TradingAccount | null, permission: 'view' | 'trade' | 'manage'): boolean => {
  if (!account) return false
  return account.permissions.includes(permission)
}
